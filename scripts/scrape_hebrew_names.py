"""
Scrape Hebrew player names from basket.co.il for every player id in data.json.

Each player.asp?PlayerId=<id>&lang=he page carries the Hebrew name in its
og:title meta tag (present even for players with no English name registered).
Output is a flat {"<player_id>": "<hebrew name>"} map, merged into
data/hebrew_names.json under "players" so export_dashboard_data.py picks it up
for every season (the site PlayerId == the canonical players.player_id).

    cd basketball-analytics
    python scripts/scrape_hebrew_names.py                 # all ids in data.json
    python scripts/scrape_hebrew_names.py --limit 20 --delay 0.3   # smoke test
    python scripts/scrape_hebrew_names.py --no-merge      # write the side file only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from html import unescape

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_JSON = ROOT / "data.json"
HE_JSON = ROOT / "data" / "hebrew_names.json"
SIDE_JSON = ROOT / "data" / "hebrew_names_scraped.json"
CACHE = ROOT / ".hebrew_cache"
BASE = "https://basket.co.il/player.asp"
UA = "basketball-analytics scraper (personal project; noamt676@gmail.com)"

_OG = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.I)
_OG2 = re.compile(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"', re.I)


# The curated 2023-2024 season already ships hand-checked Hebrew names and uses
# a private 100-113 id remap for one club, which does NOT match the live site —
# never scrape against those ids.
SKIP_SEASONS = {"2023-2024"}


def player_ids(data_json: Path) -> list[int]:
    doc = json.loads(data_json.read_text(encoding="utf-8"))
    ids: set[int] = set()
    for season, blob in doc.get("seasons", {}).items():
        if season in SKIP_SEASONS:
            continue
        for p in blob.get("players", []):
            ids.add(int(p["id"]))
        for p in blob.get("playoffs", {}).get("players", []):
            ids.add(int(p["id"]))
    return sorted(ids)


def hebrew_name(html: str) -> str | None:
    m = _OG.search(html) or _OG2.search(html)
    if not m:
        return None
    name = re.sub(r"\s+", " ", unescape(m.group(1))).strip()
    # reject obvious non-names (the generic site title starts with this)
    if not name or name.startswith("הליגה") or "מנהלת" in name:
        return None
    # keep only rows that actually contain Hebrew letters
    return name if re.search(r"[֐-׿]", name) else None


def fetch(session: requests.Session, pid: int, delay: float, last: list[float]) -> str:
    cf = CACHE / f"{pid}.html"
    if cf.exists():
        return cf.read_text(encoding="utf-8", errors="replace")
    wait = delay - (time.monotonic() - last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            r = session.get(BASE, params={"PlayerId": pid, "lang": "he"}, timeout=30)
            last[0] = time.monotonic()
            r.raise_for_status()
            r.encoding = "utf-8"  # server/requests otherwise mis-guesses -> mojibake
            CACHE.mkdir(exist_ok=True)
            cf.write_text(r.text, encoding="utf-8")
            return r.text
        except requests.RequestException as exc:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
            print(f"  ! {pid} retry ({exc})", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-merge", action="store_true", help="write the side file only, don't touch hebrew_names.json")
    args = ap.parse_args()

    ids = player_ids(DATA_JSON)
    if args.limit:
        ids = ids[: args.limit]
    print(f"{len(ids)} player ids to resolve (delay {args.delay}s)")

    session = requests.Session()
    session.headers["User-Agent"] = UA
    out: dict[str, str] = {}
    if SIDE_JSON.exists():
        out = json.loads(SIDE_JSON.read_text(encoding="utf-8"))

    last = [0.0]
    miss = 0
    for i, pid in enumerate(ids, 1):
        if str(pid) in out:
            continue
        try:
            html = fetch(session, pid, args.delay, last)
        except Exception as exc:
            print(f"  !! {pid} failed: {exc}", file=sys.stderr)
            miss += 1
            continue
        name = hebrew_name(html)
        if name:
            out[str(pid)] = name
        else:
            miss += 1
        if i % 100 == 0:
            SIDE_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            print(f"  [{i}/{len(ids)}] resolved {len(out)}, unresolved {miss}")

    SIDE_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"done: {len(out)} names, {miss} unresolved -> {SIDE_JSON.name}")

    if not args.no_merge:
        he = json.loads(HE_JSON.read_text(encoding="utf-8"))
        players = he.setdefault("players", {})
        added = 0
        for pid, name in out.items():
            if pid not in players:
                players[pid] = name
                added += 1
        HE_JSON.write_text(json.dumps(he, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"merged {added} new names into {HE_JSON.name} (players now {len(players)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
