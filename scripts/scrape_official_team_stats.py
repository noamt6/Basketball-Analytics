"""
Scrape the OFFICIAL per-game team statistics from basket.co.il's team stats
board (stats-teams.asp) for every season, and patch them into data.json as the
single source of truth for team metrics.

Why: the multi-season scraper (scrape_league.py) builds Team_Stats by *summing
the scraped player rows*. A player traded mid-season carries his whole-season
totals to whichever club his roster row lands on, which inflates that club's
team totals (e.g. Bnei Herzliya 2025-26 read 101.3 PPG instead of the official
93.1). The team board gives the real per-game averages directly.

The team board exposes per-game counting stats + shooting percentages, but no
makes/attempts and no minutes -- so this script overrides the headline
per-game / rate fields and GP from the official row, and rescales the existing
(player-summed) FGM/FGA/3PM/3PA/FTM/FTA so their point total matches the
official PTS and the derived percentages match the official 2P%/3P%/FT%. The
downstream shot-diet / four-factors / possession math then works off numbers
that reconcile with the official box score.

    cd basketball-analytics
    python scripts/scrape_official_team_stats.py              # scrape + write data/official_team_stats.json + patch data.json
    python scripts/scrape_official_team_stats.py --scrape-only # just refresh the json
    python scripts/scrape_official_team_stats.py --check       # report diffs, patch nothing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
DATA_JSON = ROOT / "data.json"
OFFICIAL_JSON = ROOT / "data" / "official_team_stats.json"
CACHE = ROOT / ".scrape_cache"
UA = "basketball-analytics scraper (personal project; noamt676@gmail.com)"
BASE = "https://basket.co.il/stats-teams.asp"
_TEAM_ID = re.compile(r"team\.asp\?TeamId=(\d+)", re.I)
_NUM = re.compile(r"-?\d+(?:\.\d+)?")

# season "2025-2026" -> cYear 2026
def season_to_cyear(season: str) -> int:
    return int(season.split("-")[1])


def _get(cyear: int, playoffs: bool, delay: float) -> str:
    board = "&StatsBoard=2" if playoffs else ""
    key = f"stats-teams_{cyear}{'_po' if playoffs else ''}.html"
    cf = CACHE / key
    if cf.exists():
        return cf.read_text(encoding="utf-8", errors="replace")
    time.sleep(delay)
    r = requests.get(BASE, params={"cYear": cyear, **({"StatsBoard": 2} if playoffs else {})},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    CACHE.mkdir(exist_ok=True)
    cf.write_text(r.text, encoding="utf-8")
    return r.text


# 17-cell main row: name, GP, PTS, 2P%, 3P%, FT%, DREB, OREB, REB, FF, FA,
# STL, TOV, AST, BLKfor, BLKagainst, PIR  -- all per game except GP.
_COLS = ["name", "gp", "pts", "p2_pct", "p3_pct", "ft_pct", "dreb", "oreb", "reb",
         "ff", "fa", "stl", "tov", "ast", "blk", "blk_against", "pir"]


def parse_team_board(html: str) -> dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for tr in soup.find_all("tr"):
        a = tr.find("a", href=_TEAM_ID)
        if not a:
            continue
        tid = _TEAM_ID.search(a["href"]).group(1)
        cells = [re.sub(r"\s+", " ", td.get_text()).strip() for td in tr.find_all("td")]
        if len(cells) < 17 or not cells[1].isdigit():
            continue
        vals = {}
        for i, k in enumerate(_COLS[1:], start=1):
            m = _NUM.search(cells[i].replace("%", ""))
            vals[k] = float(m.group()) if m else 0.0
        vals["gp"] = int(vals["gp"])
        vals["name_he"] = re.sub(r"\s+", " ", a.get_text()).strip()
        out[tid] = vals
    return out


def scrape_all(seasons: list[str], delay: float) -> dict:
    doc: dict[str, dict] = {}
    for s in seasons:
        cy = season_to_cyear(s)
        doc.setdefault(s, {})
        for po in (False, True):
            try:
                board = parse_team_board(_get(cy, po, delay))
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {s} {'PO' if po else 'RS'}: {exc}", file=sys.stderr)
                board = {}
            doc[s]["playoffs" if po else "regular"] = board
            print(f"  {s} {'PO' if po else 'RS'}: {len(board)} teams")
    return doc


# --------------------------------------------------------------------------- #
# 2023-2024 ships from the hand-curated official workbook (data/Basketball_Analytics.xlsx)
# and already carries the official team box score -- leave it untouched.
SKIP_SEASONS = {"2023-2024"}


def patch_data_json(official: dict, check_only: bool) -> int:
    d = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    diffs = 0
    patched = 0
    for season, blob in d.get("seasons", {}).items():
        if season in SKIP_SEASONS:
            continue
        off_season = official.get(season, {})
        for comp, off_map in (("regular", off_season.get("regular", {})),
                              ("playoffs", off_season.get("playoffs", {}))):
            teams = blob["teams"] if comp == "regular" else blob.get("playoffs", {}).get("teams", [])
            for t in teams:
                off = off_map.get(str(t["id"]))
                if not off:
                    # 2023-2024 uses club-code ids ("BNH"); match by Hebrew name
                    off = next((v for v in off_map.values() if v.get("name_he") == t.get("label_he")
                                or v.get("name_he") == t.get("name_he")), None)
                if not off:
                    continue
                gp = off["gp"] or t.get("gp") or 1
                new = {
                    "gp": gp,
                    "avg_points": round(off["pts"], 2),
                    "avg_assists": round(off["ast"], 2),
                    "avg_rebounds": round(off["reb"], 2),
                    "avg_oreb": round(off["oreb"], 2),
                    "avg_dreb": round(off["dreb"], 2),
                    "avg_turnovers": round(off["tov"], 2),
                    "avg_blocks": round(off["blk"], 2),
                    "avg_pir": round(off["pir"], 2),
                    "fg3_pct": round(off["p3_pct"], 1),
                }
                # rescale the player-summed makes/attempts to the official point total,
                # then re-derive makes from the official shooting percentages.
                cur_pts = 2 * (t.get("fgm", 0) - t.get("fg3m", 0)) + 3 * t.get("fg3m", 0) + t.get("ftm", 0)
                off_pts_total = off["pts"] * gp
                scale = (off_pts_total / cur_pts) if cur_pts else 1.0
                fga = round(t.get("fga", 0) * scale)
                fg3a = round(t.get("fg3a", 0) * scale)
                fta = round(t.get("fta", 0) * scale)
                two_a = max(0, fga - fg3a)
                fg3m = round(off["p3_pct"] / 100 * fg3a)
                two_m = round(off["p2_pct"] / 100 * two_a)
                ftm = round(off["ft_pct"] / 100 * fta)
                fgm = two_m + fg3m
                # reconcile PTS exactly by nudging FT makes (1 pt each)
                pts_total = round(off_pts_total)
                ftm += pts_total - (2 * two_m + 3 * fg3m + ftm)
                ftm = max(0, min(ftm, fta))
                new.update({
                    "pts": pts_total,
                    "ast": round(off["ast"] * gp),
                    "reb": round(off["reb"] * gp),
                    "oreb": round(off["oreb"] * gp),
                    "dreb": round(off["dreb"] * gp),
                    "tov": round(off["tov"] * gp),
                    "avg_fg3a": round(fg3a / gp, 2),
                    "avg_fg3m": round(fg3m / gp, 2),
                    "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta,
                    "fg3_pct": round(off["p3_pct"], 1),
                })
                if "min" in t and t["min"]:
                    new["min"] = round(t["min"] * (gp / t["gp"])) if t.get("gp") else t["min"]
                for k, v in new.items():
                    if k in t and abs((t[k] or 0) - (v or 0)) > 0.05:
                        diffs += 1
                        if check_only and diffs <= 40:
                            print(f"  {season}/{comp} {t.get('label', t['id'])} {k}: {t.get(k)} -> {v}")
                    if not check_only:
                        t[k] = v
                if not check_only:
                    patched += 1
    if check_only:
        print(f"\n{diffs} field diffs vs official (nothing written)")
        return 0
    DATA_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {patched} team rows in data.json ({diffs} fields changed)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--scrape-only", action="store_true")
    ap.add_argument("--check", action="store_true", help="report diffs, patch nothing")
    args = ap.parse_args()

    d = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    seasons = sorted(d["seasons"])
    print(f"seasons: {', '.join(seasons)}")
    official = scrape_all(seasons, args.delay)
    OFFICIAL_JSON.write_text(json.dumps(official, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {OFFICIAL_JSON.relative_to(ROOT)}")
    if args.scrape_only:
        return 0
    return patch_data_json(official, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
