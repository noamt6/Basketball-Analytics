"""
scrape_league.py — standalone multi-season scraper for basket.co.il
(Israeli Basketball Premier / "Winner" League), the same source the original
data/Basketball_Analytics.xlsx was hand-built from.

WHY THIS EXISTS
---------------
`ingest.py` loads ONE season from a hand-made workbook. To cover the last ~10
seasons we need the data pulled straight from the league site. This module does
only the *fetch + normalise* half: for each requested season it scrapes

  * player season TOTALS ............ stats-accumulate.asp?cYear=<Y>&c=<page>
  * the team list + ranks ........... table.asp?cYear=<Y>
  * per-team rosters + bios ......... team.asp?TeamId=<id>&cYear=<Y>

and writes one workbook per season, `Basketball_Analytics_<season>.xlsx`, whose
sheets/columns are byte-for-byte what `ingest.py` already knows how to read
(Teams_Details, Players_Details, Roster, Team_Stats, Player_Stats). So the flow
stays:

    python scrape_league.py --seasons 2016-2017..2025-2026 --out-dir data/scraped
    for f in data/scraped/*.xlsx: SEASON=<s> WORKBOOK=<f> python ingest.py
    # or let this script chain straight into ingest with --ingest

Nothing here touches the DB unless you pass --ingest, and it never touches the
dashboard or any frontend file.

IDENTITY
--------
The site's `PlayerId` is stable across seasons, so it is used directly as the
canonical `players.player_id` (and `ingest.build_player_id_map` then makes the
identity map for each season). The site's per-season team id (from table.asp,
e.g. 1039..1050 for 2022-23) is used as `teams.team_id`; note it is a *season*
registration id, so the same franchise can carry different ids in different
seasons — matching the "unstable id" situation schema.sql already documents.

KNOWN GAPS (documented, deliberate, safe to fill in later)
---------------------------------------------------------
* competition: only 'regular_season' is scraped. Playoffs live behind a
  different StatsBoard/board param on the site and are out of scope here.
* team season TOTALS: the site's team page is per-game and gives percentages
  only (no makes), so `Team_Stats` is AGGREGATED from the scraped player rows
  (sum per team, percentages recomputed). Team-level rebounds / bench noise
  mean this won't tie out to the site exactly — `scripts/check_data_quality.py`
  check 2 is the yardstick, same as for the shipped workbook.
* Teams_Details city / sponsor / arena and Roster.years_on_team are not on the
  scraped pages -> written as NULL (all nullable in schema.sql).
* Nationality comes from each player's own page; skip those fetches with
  --skip-bios (nationality then NULL).

All parsing is isolated in pure `parse_*(html) -> rows` functions so that when
the site's markup shifts you fix one function, not the whole pipeline. Run with
--debug-dump to keep the raw HTML for inspection.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - dependency hint
    sys.exit(
        "scrape_league.py needs 'requests' and 'beautifulsoup4' "
        "(added to requirements.txt): pip install requests beautifulsoup4 lxml"
    )

BASE_URL = "https://basket.co.il"
DEFAULT_LANG = "en"
USER_AGENT = (
    "basketball-analytics scraper (personal analytics project; "
    "contact noamt676@gmail.com)"
)

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "data" / "scraped"

# --------------------------------------------------------------------------- #
# season <-> cYear                                                            #
# --------------------------------------------------------------------------- #
# The site's cYear is the calendar year the season ENDS in: cYear=2024 is the
# 2023-2024 season. `ingest.py` labels seasons "YYYY-YYYY" (default
# "2023-2024"), so that is the label produced here.

def cyear_to_season(cyear: int) -> str:
    return f"{cyear - 1}-{cyear}"


def season_to_cyear(season: str) -> int:
    m = re.fullmatch(r"(\d{4})-(\d{4})", season.strip())
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise argparse.ArgumentTypeError(
            f"season must look like 2016-2017 (consecutive years), got {season!r}"
        )
    return int(m.group(2))


def parse_seasons_arg(value: str) -> list[int]:
    """--seasons accepts 'A-B..C-D' (inclusive range) or a comma list of
    'YYYY-YYYY', or a mix. Returns sorted unique cYear ints."""
    cyears: set[int] = set()
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ".." in chunk:
            lo, hi = (season_to_cyear(p) for p in chunk.split("..", 1))
            cyears.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            cyears.add(season_to_cyear(chunk))
    return sorted(cyears)


def last_n_cyears(n: int, through_cyear: int) -> list[int]:
    return list(range(through_cyear - n + 1, through_cyear + 1))


# --------------------------------------------------------------------------- #
# HTTP with optional on-disk cache                                            #
# --------------------------------------------------------------------------- #
class Fetcher:
    def __init__(self, delay: float, cache_dir: Path | None, debug_dump: Path | None):
        self.delay = delay
        self.cache_dir = cache_dir
        self.debug_dump = debug_dump
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_call = 0.0
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        if debug_dump:
            debug_dump.mkdir(parents=True, exist_ok=True)

    def _key(self, path: str, params: dict) -> str:
        raw = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        return hashlib.sha1(raw.encode()).hexdigest()[:16] + "_" + re.sub(
            r"[^a-zA-Z0-9]+", "-", raw
        )[:80]

    def get(self, path: str, params: dict, *, label: str = "") -> str:
        params = {"lang": DEFAULT_LANG, **params}
        key = self._key(path, params)
        cache_file = (self.cache_dir / f"{key}.html") if self.cache_dir else None
        if cache_file and cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="replace")

        wait = self.delay - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{BASE_URL}/{path.lstrip('/')}"
        for attempt in range(4):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                self._last_call = time.monotonic()
                resp.raise_for_status()
                html = resp.text
                break
            except requests.RequestException as exc:
                if attempt == 3:
                    raise
                back = 2 ** attempt
                print(f"  ! {label or path} failed ({exc}); retry in {back}s", file=sys.stderr)
                time.sleep(back)

        if cache_file:
            cache_file.write_text(html, encoding="utf-8")
        if self.debug_dump:
            (self.debug_dump / f"{key}.html").write_text(html, encoding="utf-8")
        return html


# --------------------------------------------------------------------------- #
# pure parsers: html -> list[dict]                                            #
# --------------------------------------------------------------------------- #
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_MAKE_ATT = re.compile(r"(\d+)\s*/\s*(\d+)")
_PLAYER_ID = re.compile(r"player\.asp\?PlayerId=(\d+)", re.I)
_TEAM_ID = re.compile(r"team\.asp\?TeamId=(\d+)", re.I)


def _to_num(text: str):
    m = _NUM.search(text.replace(",", ""))
    return float(m.group()) if m and "." in m.group() else (int(m.group()) if m else None)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_standings(html: str) -> list[dict]:
    """table.asp -> [{team_id, team_name, rank}] for every team that season."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, dict] = {}
    for a in soup.find_all("a", href=_TEAM_ID):
        tid = _TEAM_ID.search(a["href"]).group(1)
        name = _clean(a.get_text())
        if not name or tid in seen:
            continue
        seen[tid] = {"team_id": tid, "team_name": name, "rank": len(seen) + 1}
    return list(seen.values())


# Column order of the numeric <td>s on stats-accumulate.asp, AFTER the leading
# rank / player-link / team-link cells. Verified against cYear=2023.
_ACC_COLS = [
    "gp", "min", "pts",
    "two_ma", "two_pct",
    "fg3_ma", "fg3_pct",
    "ft_ma", "ft_pct",
    "dreb", "oreb", "reb",
    "ff", "fa",
    "stl", "tov", "ast",
    "blk", "bka",
    "pir",
]


def parse_player_totals_page(html: str) -> list[dict]:
    """One page of stats-accumulate.asp. Returns normalised season-total rows
    keyed by the schema-facing names (fgm/fga/fg3m/... , 'source_player_id',
    'team_name'). Two-pointers and threes are summed into fgm/fga."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        pa = tr.find("a", href=_PLAYER_ID)
        if not pa:
            continue
        ta = tr.find("a", href=_TEAM_ID)  # this page has no team column, but be tolerant
        cells = tr.find_all("td")
        texts = [_clean(td.get_text()) for td in cells]
        # numeric cells are everything AFTER the cell holding the player link
        # (leading cells: rank, player name; no team column on stats-accumulate)
        try:
            name_idx = next(i for i, td in enumerate(cells) if td.find("a", href=_PLAYER_ID))
        except StopIteration:
            continue
        nums = [t for t in texts[name_idx + 1:] if t != ""]
        if len(nums) < len(_ACC_COLS):
            continue
        raw = dict(zip(_ACC_COLS, nums))

        two_m, two_a = _split_ma(raw["two_ma"])
        fg3m, fg3a = _split_ma(raw["fg3_ma"])
        ftm, fta = _split_ma(raw["ft_ma"])
        fgm = _add(two_m, fg3m)
        fga = _add(two_a, fg3a)
        rows.append({
            "source_player_id": int(_PLAYER_ID.search(pa["href"]).group(1)),
            "player_name": _clean(pa.get_text()),
            "team_name": _clean(ta.get_text()) if ta else None,
            "gp": _to_num(raw["gp"]), "min": _to_num(raw["min"]), "pts": _to_num(raw["pts"]),
            "fgm": fgm, "fga": fga, "fg_pct": _pct(fgm, fga),
            "fg3m": fg3m, "fg3a": fg3a, "fg3_pct": _to_num(raw["fg3_pct"]),
            "ftm": ftm, "fta": fta, "ft_pct": _to_num(raw["ft_pct"]),
            "oreb": _to_num(raw["oreb"]), "dreb": _to_num(raw["dreb"]), "reb": _to_num(raw["reb"]),
            "ast": _to_num(raw["ast"]), "tov": _to_num(raw["tov"]),
            "stl": _to_num(raw["stl"]), "blk": _to_num(raw["blk"]),
            "pir": _to_num(raw["pir"]),
        })
    return rows


def parse_accumulate_page_count(html: str) -> int:
    """Highest '&c=<n>' page number linked on a stats-accumulate.asp page."""
    return max(
        (int(m) for m in re.findall(r"[?&]c=(\d+)", html)),
        default=1,
    )


_HEIGHT = re.compile(r"(\d\.\d{2})")
_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_team_roster(html: str) -> list[dict]:
    """team.asp -> [{source_player_id, player_name, jersey_number, position,
    height_m, birth_date}].

    Each player is a `<div class="box_role">` holding a player.asp <a> with an
    `<img alt="First Last">`, a `.role_num` (jersey), a `.role_name`
    ("First<br>Last"), and a `.role_desc` whose <strong> is "G | 1.91" and
    whose trailing text is the birth date dd/mm/yyyy. Coaches reuse box_role
    but link to all-time-coaches.asp, so require the player link.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: dict[int, dict] = {}
    for box in soup.find_all("div", class_="box_role"):
        a = box.find("a", href=_PLAYER_ID)
        if not a:
            continue
        pid = int(_PLAYER_ID.search(a["href"]).group(1))
        if pid in out:
            continue

        img = box.find("img", alt=True)
        role_name = box.find("div", class_="role_name")
        if img and _clean(img["alt"]):
            name = _clean(img["alt"])
        elif role_name:
            name = _clean(role_name.get_text(" "))
        else:
            name = _clean(a.get_text(" "))

        num = box.find("div", class_="role_num")
        jersey = int(_NUM.search(num.get_text()).group()) if num and _NUM.search(num.get_text()) else None

        desc = box.find("div", class_="role_desc")
        desc_txt = _clean(desc.get_text(" ")) if desc else ""
        pos = None
        pm = re.search(r"([PSC]?[GFC])\s*\|", desc_txt)
        if pm:
            pos = pm.group(1)
        hm = _HEIGHT.search(desc_txt)
        height_m = float(hm.group(1)) if hm else None
        dm = _DATE.search(desc_txt)
        birth_date = None
        if dm:
            d, mth, y = (int(x) for x in dm.groups())
            birth_date = f"{y:04d}-{mth:02d}-{d:02d}"  # site is day/month/year

        out[pid] = {
            "source_player_id": pid, "player_name": name, "jersey_number": jersey,
            "position": pos, "height_m": height_m, "birth_date": birth_date,
        }
    return list(out.values())


def parse_player_nationality(html: str) -> str | None:
    """player.asp shows nationality only as a flag image right after the
    "Nationality:" label: `... Nationality: <a ...><img src="Pics/flags/..."
    alt="United States" />`. Take that alt text."""
    m = re.search(
        r'Nationality:.*?flags/[^"\']*["\'][^>]*\balt=["\']([^"\']+)["\']',
        html, re.I | re.S,
    )
    return _clean(m.group(1)) if m else None


def _split_ma(text: str):
    m = _MAKE_ATT.search(text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _add(a, b):
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


def _pct(made, att):
    return round(100 * made / att, 1) if made is not None and att else None


def _split_name(full: str) -> tuple[str, str]:
    full = _clean(full)
    if "," in full:  # "Last, First"
        last, first = (p.strip() for p in full.split(",", 1))
        return first, last
    parts = full.split(" ")
    return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (full, full)


# --------------------------------------------------------------------------- #
# per-season orchestration -> ingest-shaped DataFrames                        #
# --------------------------------------------------------------------------- #
def scrape_season(fetch: Fetcher, cyear: int, *, skip_bios: bool, limit: int | None) -> dict[str, pd.DataFrame]:
    season = cyear_to_season(cyear)
    print(f"[{season}] cYear={cyear}")

    standings = parse_standings(fetch.get("table.asp", {"cYear": cyear}, label=f"{season} standings"))
    if not standings:
        raise RuntimeError(f"{season}: no teams parsed from table.asp — markup may have changed")
    team_by_name = {t["team_name"]: t["team_id"] for t in standings}
    print(f"  teams: {len(standings)}")

    # ---- player season totals (paginated by &c=) ----
    first = fetch.get("stats-accumulate.asp", {"cYear": cyear, "c": 1}, label=f"{season} totals p1")
    pages = parse_accumulate_page_count(first)
    player_rows = parse_player_totals_page(first)
    for c in range(2, pages + 1):
        html = fetch.get("stats-accumulate.asp", {"cYear": cyear, "c": c}, label=f"{season} totals p{c}")
        player_rows.extend(parse_player_totals_page(html))
        if limit and len(player_rows) >= limit:
            break
    if limit:
        player_rows = player_rows[:limit]
    if not player_rows:
        raise RuntimeError(f"{season}: no player rows parsed from stats-accumulate.asp")
    print(f"  player season-total rows: {len(player_rows)} across {pages} page(s)")

    # ---- rosters + bios, per team ----
    roster_rows: list[dict] = []
    bio_by_id: dict[int, dict] = {}
    for t in standings:
        html = fetch.get("team.asp", {"TeamId": t["team_id"], "cYear": cyear},
                         label=f"{season} roster {t['team_name']}")
        for r in parse_team_roster(html):
            bio_by_id.setdefault(r["source_player_id"], r)
            roster_rows.append({
                "PlayerId": r["source_player_id"], "TeamID": t["team_id"],
                "Position": r["position"], "JerseyNumber": r["jersey_number"],
                "YearsOnTeam": None,
            })
    print(f"  roster rows: {len(roster_rows)}")

    # players seen in stats but not on any scraped roster still need identity rows
    for pr in player_rows:
        pid = pr["source_player_id"]
        if pid not in bio_by_id:
            first_n, last_n = _split_name(pr["player_name"])
            bio_by_id[pid] = {
                "source_player_id": pid, "player_name": pr["player_name"],
                "jersey_number": None, "position": None, "height_m": None, "birth_date": None,
            }

    nationality: dict[int, str | None] = {}
    if not skip_bios:
        # in a --limit smoke run, only fetch bios for the players we kept
        bio_ids = ({pr["source_player_id"] for pr in player_rows} & set(bio_by_id)
                   if limit else list(bio_by_id))
        for pid in bio_ids:
            html = fetch.get("player.asp", {"PlayerId": pid}, label=f"{season} bio {pid}")
            nationality[pid] = parse_player_nationality(html)

    # ---------------- assemble ingest-shaped frames ---------------- #
    teams_df = pd.DataFrame(
        [{"TeamID": t["team_id"], "TeamName": t["team_name"],
          "City": None, "MainSponsor": None, "Arena": None} for t in standings]
    )

    players_df = pd.DataFrame([
        {
            "PlayerId": pid,
            "FirstName": _split_name(b["player_name"])[0],
            "LastName": _split_name(b["player_name"])[1],
            "Nationality": nationality.get(pid),
            "BirthDate": b["birth_date"],
            "Height": b["height_m"],
        }
        for pid, b in bio_by_id.items()
    ])

    roster_df = pd.DataFrame(roster_rows).drop_duplicates(subset=["PlayerId"], keep="first")

    stat_cols = ["GP", "MIN", "PTS", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%",
                 "FTM", "FTA", "FT%", "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "PIR"]
    key_map = {"gp": "GP", "min": "MIN", "pts": "PTS", "fgm": "FGM", "fga": "FGA",
               "fg_pct": "FG%", "fg3m": "3PM", "fg3a": "3PA", "fg3_pct": "3P%",
               "ftm": "FTM", "fta": "FTA", "ft_pct": "FT%", "oreb": "OREB",
               "dreb": "DREB", "reb": "REB", "ast": "AST", "tov": "TOV",
               "stl": "STL", "blk": "BLK", "pir": "PIR"}

    player_stats_df = pd.DataFrame([
        {"PlayerId": pr["source_player_id"], **{key_map[k]: pr[k] for k in key_map}}
        for pr in player_rows
    ])

    # Team_Stats: aggregated from player rows (see KNOWN GAPS in the docstring).
    ps = player_stats_df.copy()
    ps["TeamID"] = ps["PlayerId"].map(
        {r["PlayerId"]: r["TeamID"] for r in roster_rows}
    )
    agg_cols = [c for c in stat_cols if c not in ("FG%", "3P%", "FT%")]
    grouped = ps.dropna(subset=["TeamID"]).groupby("TeamID")[agg_cols].sum(min_count=1).reset_index()
    grouped["GP"] = ps.dropna(subset=["TeamID"]).groupby("TeamID")["GP"].max().values  # team GP, not sum
    grouped["FG%"] = (100 * grouped["FGM"] / grouped["FGA"]).round(1)
    grouped["3P%"] = (100 * grouped["3PM"] / grouped["3PA"]).round(1)
    grouped["FT%"] = (100 * grouped["FTM"] / grouped["FTA"]).round(1)
    team_stats_df = grouped.rename(columns={"TeamID": "TeamId"})[["TeamId", *stat_cols]]

    # keep integer columns as nullable ints so the workbook (and then the
    # INTEGER schema columns) don't get "3.0" floats from NaN-widening.
    int_stats = [c for c in stat_cols if c not in ("FG%", "3P%", "FT%")]
    for df, cols in ((roster_df, ["JerseyNumber", "YearsOnTeam"]),
                     (player_stats_df, int_stats), (team_stats_df, int_stats)):
        for c in cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")

    return {
        "Teams_Details": teams_df,
        "Players_Details": players_df,
        "Roster": roster_df,
        "Team_Stats": team_stats_df,
        "Player_Stats": player_stats_df,
        "_season": season,  # popped by the writer
    }


def write_workbook(frames: dict[str, pd.DataFrame], out_dir: Path) -> Path:
    season = frames.pop("_season")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"Basketball_Analytics_{season}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for sheet, df in frames.items():
            df.to_excel(xw, sheet_name=sheet, index=False)
    print(f"  -> {path}  ({', '.join(f'{k}:{len(v)}' for k, v in frames.items())})")
    return path


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape basket.co.il season totals / rosters into ingest-ready workbooks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--seasons", type=parse_seasons_arg, default=None,
                   help="e.g. '2016-2017..2025-2026' or '2021-2022,2022-2023'")
    p.add_argument("--last", type=int, default=10, help="last N seasons (used when --seasons omitted)")
    p.add_argument("--through", type=season_to_cyear, default=2026,
                   help="most recent season for --last, as YYYY-YYYY (default 2025-2026)")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--delay", type=float, default=1.5, help="seconds between HTTP requests")
    p.add_argument("--cache-dir", type=Path, default=HERE / ".scrape_cache",
                   help="reuse fetched HTML across runs; pass '' to disable")
    p.add_argument("--debug-dump", type=Path, default=None, help="also save every fetched page here")
    p.add_argument("--skip-bios", action="store_true",
                   help="don't fetch per-player pages (nationality left NULL)")
    p.add_argument("--limit", type=int, default=None, help="cap player rows per season (smoke test)")
    p.add_argument("--dry-run", action="store_true", help="scrape + report counts, write nothing")
    p.add_argument("--ingest", action="store_true",
                   help="after writing each workbook, load it via ingest.run() (needs a live DB / .env)")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    cyears = args.seasons or last_n_cyears(args.last, args.through)
    cache_dir = args.cache_dir if str(args.cache_dir) not in ("", ".") else None
    fetch = Fetcher(args.delay, cache_dir, args.debug_dump)

    print(f"seasons: {', '.join(cyear_to_season(c) for c in cyears)}")
    written: list[tuple[str, Path]] = []
    failures: list[tuple[str, str]] = []
    for cyear in cyears:
        season = cyear_to_season(cyear)
        try:
            frames = scrape_season(fetch, cyear, skip_bios=args.skip_bios, limit=args.limit)
        except Exception as exc:  # keep going; report at the end
            failures.append((season, str(exc)))
            print(f"  !! {season} failed: {exc}", file=sys.stderr)
            continue
        if args.dry_run:
            frames.pop("_season", None)
            continue
        path = write_workbook(frames, args.out_dir)
        written.append((season, path))

    if args.ingest and written:
        import ingest  # local import: only needed on the --ingest path
        for season, path in written:
            os.environ["SEASON"] = season
            print(f"[ingest] {season} <- {path.name}")
            ingest.run(path)

    print("\n=== summary ===")
    for season, path in written:
        print(f"  ok   {season}  {path}")
    for season, msg in failures:
        print(f"  FAIL {season}  {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
