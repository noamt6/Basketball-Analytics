#!/usr/bin/env python3
"""
scrape_player_details.py -- backfill missing jersey numbers (and normalise
nickname punctuation) directly into the deployed ``data.json``.

WHY
---
``data.json`` is produced by ``export_dashboard_data.py`` from the DB, which is
loaded from the per-season workbooks scraped by ``scrape_league.py``. The
``stats-accumulate.asp`` season-totals tables that feed the workbooks carry NO
jersey number, so any player who is not also on the club's roster widget
(``team.asp``) lands with ``jersey = null`` / ``0`` -- ~25 % of all player-rows
today (call-ups, mid-season signings/releases, youth).

This tool closes the gap without needing a live DB: for every ``(season, team)``
that still has a jersey hole it re-reads the season-accurate roster widget
``team.asp?TeamId=<id>&cYear=<endYear>`` (same page, cache dir and cache key as
``scrape_league.Fetcher`` -- 126 of them are already cached under
``.scrape_cache/``), maps ``PlayerId -> shirt number`` from the ``box_role``
blocks, and patches the matching player rows in ``data.json`` in place
(regular-season and playoff sub-blobs alike).

It also standardises nickname quoting: an English ``First "Nick" Last`` keeps
straight quotes; the Hebrew ``name_he`` equivalent is rewritten to gershayim
(``First ״Nick״ Last``), the correct Hebrew typographic convention. The nickname
itself is always preserved -- see the ``dashboard.html`` ``playerHay`` change
that makes the plain (nickname-stripped) name searchable too.

USAGE
-----
    python scripts/scrape_player_details.py               # cache-first, fetch holes
    python scripts/scrape_player_details.py --offline     # never hit the network
    python scripts/scrape_player_details.py --dry-run     # report only, no write
    python scripts/scrape_player_details.py --delay 1.0   # politeness between fetches

Writes back ``data.json`` (same ``json.dumps(ensure_ascii=False, indent=2)+"\n"``
shape as the exporter) and an audit sidecar ``data/resolved_jerseys.json``
(``"<season>|<pid>": <jersey>``). Exit 0 always unless something genuinely broke;
the summary line reports resolved / still-missing counts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

# Reuse the exact cache key + season<->cYear mapping the league scraper uses, so
# this shares .scrape_cache/ with it and never double-fetches.
import scrape_league as SL  # noqa: E402

BASE_URL = "https://basket.co.il"
CACHE_DIR = ROOT / ".scrape_cache"

# One <div class="box_role"> ... </a> player block (team.asp roster widget AND
# the player.asp squad widget both use it): capture PlayerId then the role_num
# shirt number, without letting the gap run into the next box_role block.
_BOX_RE = re.compile(
    r'class="(?:item )?box_role">\s*<a href="player\.asp\?PlayerId=(\d+)[^"]*"\s*>'
    r'(?:(?!box_role">).)*?role_num[^>]*>\s*(\d*)\s*<',
    re.S | re.I,
)
_NICK_STRAIGHT = re.compile(r'"([^"\r\n]{1,40})"')


def cache_key(team_id: str, cyear: int) -> str:
    # mirrors scrape_league.Fetcher._key({'lang':'en','TeamId':..,'cYear':..})
    params = {"lang": "en", "TeamId": team_id, "cYear": cyear}
    raw = "team.asp?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    import hashlib
    return hashlib.sha1(raw.encode()).hexdigest()[:16] + "_" + re.sub(
        r"[^a-zA-Z0-9]+", "-", raw
    )[:80]


def load_roster_html(team_id: str, cyear: int, *, offline: bool, delay: float,
                     session) -> str | None:
    cf = CACHE_DIR / f"{cache_key(team_id, cyear)}.html"
    if cf.exists():
        return cf.read_text(encoding="utf-8", errors="replace")
    if offline:
        return None
    if session is None:
        return None
    time.sleep(delay)
    url = f"{BASE_URL}/team.asp"
    try:
        resp = session.get(url, params={"lang": "en", "TeamId": team_id,
                                        "cYear": cyear}, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! team {team_id} cYear={cyear} fetch failed: {exc}",
              file=sys.stderr)
        return None
    html = resp.text
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf.write_text(html, encoding="utf-8")
    return html


def jerseys_from_html(html: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for m in _BOX_RE.finditer(html):
        pid = int(m.group(1))
        num = m.group(2)
        if pid in out:
            continue
        if num and num.isdigit():
            out[pid] = int(num)
    return out


# Known unrecoverable source rows: a player-stint whose points/rebounds/assists
# came through but whose entire made/attempted shot box is absent (0/0/0/0/0/0),
# so PTS can't satisfy 2·(FGM−FG3M)+3·FG3M+FTM. There is no free source to
# reconstruct the split, so we flag it with the existing `bad_split` mechanism
# (dashboard already warns + drops eFG%/TS% for these) instead of fabricating.
KNOWN_BAD_SPLIT = {
    ("2023-2024", 13367),  # Daniel Rosenbaum, HGE stint — pts=46 with an empty shot box
}


def normalise_nick_he(name_he: str) -> str:
    """Straight-quoted nickname -> Hebrew gershayim (U+05F4). Idempotent."""
    if not name_he or '"' not in name_he:
        return name_he
    return _NICK_STRAIGHT.sub(lambda m: "״" + m.group(1) + "״", name_he)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data.json")
    ap.add_argument("--sidecar", type=Path, default=ROOT / "data" / "resolved_jerseys.json")
    ap.add_argument("--delay", type=float, default=0.8, help="seconds between network fetches")
    ap.add_argument("--offline", action="store_true", help="cache only, never fetch")
    ap.add_argument("--dry-run", action="store_true", help="report only, do not write")
    args = ap.parse_args()

    doc = json.loads(args.data.read_text(encoding="utf-8"))
    seasons = doc["seasons"]

    # (season, team_id) -> holes ; and every player row object that needs a number
    holes: dict[tuple[str, str], list] = {}

    def collect(season: str, players: list):
        for p in players:
            if p.get("jersey") in (None, 0, "0", ""):
                holes.setdefault((season, str(p.get("team_id"))), []).append(p)

    for sk, s in seasons.items():
        collect(sk, s.get("players", []))
        collect(sk, (s.get("playoffs") or {}).get("players", []))

    total_holes = sum(len(v) for v in holes.values())
    pairs = sorted(holes)
    print(f"missing jersey: {total_holes} player-rows across {len(pairs)} "
          f"(season, team) pairs")

    session = None
    if not args.offline:
        try:
            import requests
            session = requests.Session()
            session.headers["User-Agent"] = getattr(SL, "USER_AGENT", "Mozilla/5.0")
        except ImportError:
            print("  ! requests not installed -- running --offline", file=sys.stderr)

    resolved: dict[str, int] = {}
    nick_fixes = 0
    fetched = from_cache = no_page = 0

    for (sk, tid) in pairs:
        cyear = SL.season_to_cyear(sk)
        cf = CACHE_DIR / f"{cache_key(tid, cyear)}.html"
        had_cache = cf.exists()
        html = load_roster_html(tid, cyear, offline=args.offline, delay=args.delay,
                                session=session)
        if html is None:
            no_page += 1
            continue
        if had_cache:
            from_cache += 1
        else:
            fetched += 1
        jmap = jerseys_from_html(html)
        for p in holes[(sk, tid)]:
            j = jmap.get(p["id"])
            if j:
                p["jersey"] = j
                resolved[f"{sk}|{p['id']}"] = j

    # nickname normalisation + jersey sentinel cleanup (all rows, both blobs).
    # `0` is not a real IBSL shirt number -- collapse the stray `0`s to `null`
    # so "missing jersey" has exactly one representation for the QA audit.
    zero_to_null = 0
    bad_split_flagged = 0
    for sk, s in seasons.items():
        rows = list(s.get("players", [])) + list((s.get("playoffs") or {}).get("players", []))
        for p in rows:
            nh = p.get("name_he")
            fixed = normalise_nick_he(nh)
            if fixed != nh:
                p["name_he"] = fixed
                nick_fixes += 1
            if p.get("jersey") == 0:
                p["jersey"] = None
                zero_to_null += 1
            if (sk, p.get("id")) in KNOWN_BAD_SPLIT and not p.get("bad_split"):
                p["bad_split"] = True
                bad_split_flagged += 1

    still_missing = total_holes - len(resolved)
    print(f"  pages: {from_cache} from cache, {fetched} fetched, {no_page} unavailable")
    print(f"  jerseys resolved: {len(resolved)}   still missing: {still_missing}")
    print(f"  name_he nickname punctuation normalised: {nick_fixes}")
    print(f"  jersey 0 -> null sentinel cleanup: {zero_to_null}")
    print(f"  unrecoverable shot-box rows flagged bad_split: {bad_split_flagged}")

    if args.dry_run:
        print("dry-run: data.json not written")
        return 0

    args.data.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    wrote = str(args.data)
    if resolved:  # only leave an audit sidecar when there was something to record
        args.sidecar.parent.mkdir(parents=True, exist_ok=True)
        args.sidecar.write_text(json.dumps(dict(sorted(resolved.items())),
                                           ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        wrote += f"  and  {args.sidecar}"
    print(f"wrote {wrote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
