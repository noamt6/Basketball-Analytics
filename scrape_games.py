"""
scrape_games.py -- per-game box scores for one season -> chunked static JSON.

Pilot pipeline for the dashboard's Results / Box Score / Game Log views. It
reads the league site directly (no database) and writes, next to
dashboard.html:

    games/<season>/index.json         schedule + results (all games, all stages)
    games/<season>/g/<game_id>.json   one full box score per played game
    games/<season>/player_logs.json   columnar: one row per player per game
    games/seasons.json                manifest: which seasons have game data

Source pages (basket.co.il, English):
  * results.asp?cYear=<Y>&Board=<b> ... one fixtures/results table per
    competition board. The board <select> on the page is read to find the
    league stages (regular season, Play-In, quarter/semi/final series); Cup and
    Supercup boards are skipped.
  * game-zone.asp?GameId=<id> ......... box score: per-player rows, a "Team"
    row (team rebounds etc.), a "Total" row, quarter scores (+ OT columns),
    referees, attendance, and a "More Stats" table.

Every request goes through scrape_league.Fetcher, so pages are cached in
.scrape_cache/ (shared with the other scrapers) and the site is never hit
twice for the same page. --offline never touches the network.

Each game is validated before it is written. Hard checks (a failure leaves
the game out and is reported, never written silently): player rows + Team row
== Total row for points / 2PT / 3PT / FT, Total == the score on the results
page, sum of quarters (incl. OT periods) == score, made <= attempted.
Soft checks become `flags` on the written game: off-by-one source quirks in the
Total row for fouls / rebounds / steals etc. (e.g. a bench technical counted
only in the Total), and team minutes far from 200 + 25*OT (an abandoned game).
A game with no box score on the site at all (e.g. an awarded result) stays in
index.json with "box": false and a note.

Usage:
    python scrape_games.py --season 2025-2026 --limit 5 --out <scratch dir>
    python scrape_games.py --season 2025-2026                 # full season
    python scrape_games.py --season 2025-2026 --offline --check
    python scrape_games.py --season 2025-2026 --game-ids 26397,26401
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scrape_league import (
    DEFAULT_LANG,
    Fetcher,
    _clean,
    _split_ma,
    _to_num,
    season_to_cyear,
)

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "games"
DEFAULT_CACHE_DIR = HERE / ".scrape_cache"
DATA_JSON = HERE / "data.json"
SCHEMA_VERSION = 1

# Board option label -> stage. Order matters: "Final Series" must not be
# swallowed by the "Semi Final" / "Quarter Final" patterns.
STAGE_PATTERNS = (
    ("quarterfinal", re.compile(r"quarter\s*final", re.I)),
    ("semifinal", re.compile(r"semi\s*final", re.I)),
    ("final", re.compile(r"final\s*(series|four)?$", re.I)),
    ("playin", re.compile(r"play\s*-?\s*in", re.I)),
    ("regular", re.compile(r"^winner league$|^ligat|^super league$", re.I)),
)
SKIP_BOARDS = re.compile(r"cup", re.I)  # Winner Cup, Supercup: other competitions
REGULAR_BOARD = 5

# player_logs.json column order (kept in sync with the dashboard loader).
LOG_COLS = [
    "game_id", "player_id", "team_id", "opp_id", "home", "starter", "min", "pts",
    "fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "ast", "stl",
    "tov", "blk", "pf", "fd", "pir", "pm",
]

_GAME_ID = re.compile(r"game-zone\.asp\?GameId=(\d+)", re.I)
_TEAM_ID = re.compile(r"team\.asp\?TeamId=(\d+)", re.I)
_PLAYER_ID = re.compile(r"player\.asp\?PlayerId=(\d+)", re.I)
_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_TIME = re.compile(r"\b(\d{1,2}:\d{2})\b")
_SCORE = re.compile(r"(\d+)\s*-\s*(\d+)")
_ROUND = re.compile(r"^Game\s+(\d+)$", re.I)


class CacheMiss(RuntimeError):
    pass


class CountingFetcher(Fetcher):
    """scrape_league.Fetcher + an --offline mode and cache hit/miss counters."""

    def __init__(self, delay: float, cache_dir: Path, offline: bool):
        super().__init__(delay, cache_dir, None)
        self.offline = offline
        self.hits = 0
        self.fetched = 0

    def get(self, path: str, params: dict, *, label: str = "") -> str:
        key = self._key(path, {"lang": DEFAULT_LANG, **params})
        if (self.cache_dir / f"{key}.html").exists():
            self.hits += 1
        elif self.offline:
            raise CacheMiss(f"{label or path} {params} not in cache (--offline)")
        else:
            self.fetched += 1
        return super().get(path, params, label=label)


def _txt(el) -> str:
    return _clean(el.get_text(" ")) if el is not None else ""


def _int(text: str) -> int:
    v = _to_num(text or "")
    return int(v) if v is not None else 0


# --------------------------------------------------------------------------- #
# results.asp -> boards + game list                                           #
# --------------------------------------------------------------------------- #
def parse_boards(html: str) -> list[tuple[str, int]]:
    """The competition <select> -> [(stage, board_id)] for league stages only."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": "Board"})
    out: list[tuple[str, int]] = []
    if sel is None:
        return [("regular", REGULAR_BOARD)]
    for opt in sel.find_all("option"):
        label, value = _txt(opt), opt.get("value", "0")
        if not value.isdigit() or value == "0" or SKIP_BOARDS.search(label):
            continue
        for stage, pat in STAGE_PATTERNS:
            if pat.search(label):
                out.append((stage, int(value)))
                break
        else:
            print(f"  ? unknown board {label!r} ({value}) -- skipped", file=sys.stderr)
    return out


def parse_results(html: str, stage: str) -> list[dict]:
    """One results.asp board -> [{id, stage, round, date, time, venue, home, away}].

    Round headers are single-cell "Game N" rows. Unplayed fixtures have no
    score and come back with status "scheduled" (pts None).
    """
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", href=_GAME_ID)
    if link is None:
        return []
    table = link.find_parent("table")
    games, rnd, seen = [], None, set()
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) == 1:
            m = _ROUND.match(_txt(tds[0]))
            if m:
                rnd = int(m.group(1))
            continue
        teams = [_TEAM_ID.search(a["href"]).group(1) for a in tr.find_all("a", href=_TEAM_ID)]
        glinks = tr.find_all("a", href=_GAME_ID)
        if len(teams) < 2 or not glinks:
            continue
        gid = int(_GAME_ID.search(glinks[0]["href"]).group(1))
        if gid in seen:
            continue
        seen.add(gid)
        # The score link is the game-zone <a> whose text holds "a - b".
        score_a = next((a for a in glinks if _SCORE.search(_txt(a))), None)
        home_pts = away_pts = None
        ot = 0
        if score_a is not None:
            sm = _SCORE.search(_txt(score_a))
            home_pts, away_pts = int(sm.group(1)), int(sm.group(2))
            sup = score_a.find("sup") or score_a.find_next_sibling("sup")
            if sup is not None:
                ot = _int(_txt(sup))
        dm = _DATE.search(_txt(tds[0]))
        date = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}" if dm else None
        tm = _TIME.search(_txt(tds[1]) if len(tds) > 1 else "")
        games.append({
            "id": gid,
            "stage": stage,
            "round": rnd,
            "date": date,
            "time": tm.group(1) if tm else None,
            "venue": _txt(tds[2]) if len(tds) > 2 else None,
            "status": "final" if home_pts is not None else "scheduled",
            "ot": ot,
            "home": {"team_id": teams[0], "pts": home_pts},
            "away": {"team_id": teams[1], "pts": away_pts},
        })
    return games


# --------------------------------------------------------------------------- #
# game-zone.asp -> box score                                                  #
# --------------------------------------------------------------------------- #
# Column positions in a box-score row (after the header rows):
#  0 #  1 name  2 SF  3 Min  4 Pts  5 2PT M/A  6 %  7 3PT M/A  8 %  9 1PT M/A
# 10 %  11 DR  12 OR  13 TR  14 PF  15 FA  16 ST  17 TO  18 AS  19 BKF  20 BKA
# 21 VAL  22 +/-
def _stat_row(cells: list[str]) -> dict:
    fg2m, fg2a = _split_ma(cells[5])
    fg3m, fg3a = _split_ma(cells[7])
    ftm, fta = _split_ma(cells[9])
    return {
        "min": _int(cells[3]), "pts": _int(cells[4]),
        "fg2": [fg2m or 0, fg2a or 0], "fg3": [fg3m or 0, fg3a or 0], "ft": [ftm or 0, fta or 0],
        "dreb": _int(cells[11]), "oreb": _int(cells[12]),
        "pf": _int(cells[14]), "fd": _int(cells[15]), "stl": _int(cells[16]),
        "tov": _int(cells[17]), "ast": _int(cells[18]), "blk": _int(cells[19]),
        "blka": _int(cells[20]), "pir": _int(cells[21]), "pm": _int(cells[22]),
    }


def _box_tables(soup):
    for t in soup.find_all("table", class_="stats_tbl"):
        if t.get("class") != ["stats_tbl"]:
            continue
        rows = t.find_all("tr")
        if len(rows) > 3 and _txt(rows[2]).startswith("#"):
            yield t, rows


def _quarters(soup, label: str) -> list[list[int]]:
    for t in soup.find_all("table", class_="categories"):
        rows = t.find_all("tr")
        if rows and _txt(rows[0]).lower().startswith(label):
            return [[_int(_txt(td)) for td in r.find_all("td")[1:]] for r in rows[1:3]]
    return []


def parse_box_score(html: str) -> dict:
    """game-zone.asp -> {referees, attendance, teams: [ {team_id, coach, q,
    players, team_row, total, more} x2 ]} in page order (home first)."""
    soup = BeautifulSoup(html, "html.parser")
    page = _txt(soup)

    refs = []
    m = re.search(r"Referees:\s*(.*?)(?:Observer:|$)", page)
    if m:
        refs = [r for r in (x.strip(" ,") for x in m.group(1).split(",")) if r]
        refs = [r.split("  ")[0] for r in refs][:4]
    att = re.search(r"Viewers:\s*([\d,]+)", page)

    quarters = _quarters(soup, "by quarter")
    more = {}
    for t in soup.find_all("table", class_="stats_tbl"):
        rows = t.find_all("tr")
        if rows and _txt(rows[0]).lower() == "more stats" and len(rows) >= 4:
            more = {i: [_txt(td) for td in r.find_all("td")[1:]] for i, r in enumerate(rows[2:4])}

    teams = []
    for idx, (t, rows) in enumerate(_box_tables(soup)):
        head = rows[0]
        tlink = head.find("a", href=_TEAM_ID)
        coach = re.search(r"\(Coach:\s*([^)]+)\)", _txt(head))
        players, team_row, total = [], None, None
        for tr in rows[3:]:
            cells = [_txt(td) for td in tr.find_all("td")]
            if len(cells) < 23:
                continue
            plink = tr.find("a", href=_PLAYER_ID)
            if plink is not None:
                row = _stat_row(cells)
                players.append({
                    "id": int(_PLAYER_ID.search(plink["href"]).group(1)),
                    "jersey": _int(cells[0]) if cells[0].strip() else None,
                    "name": cells[1],
                    "starter": cells[2].strip() == "*",
                    **row,
                })
            elif cells[1] == "Team":
                team_row = _stat_row(cells)
            elif cells[1] == "Total":
                total = _stat_row(cells)
        team = {
            "team_id": _TEAM_ID.search(tlink["href"]).group(1) if tlink else None,
            "name": _txt(tlink) if tlink else _txt(head),
            "coach": coach.group(1).strip() if coach else None,
            "q": quarters[idx] if idx < len(quarters) else [],
            "players": players,
            "team_row": team_row,
            "total": total,
        }
        if more.get(idx) and len(more[idx]) >= 4:
            mv = more[idx]
            team["more"] = {
                "pts_off_tov": _int(mv[0]), "pts_paint": _int(mv[1]),
                "second_chance": _int(mv[2]), "time_leading": mv[3] or None,
            }
        teams.append(team)
    return {
        "referees": refs,
        "attendance": _int(att.group(1)) if att else None,
        "teams": teams,
    }


# --------------------------------------------------------------------------- #
# validation                                                                  #
# --------------------------------------------------------------------------- #
_SOFT_SUM_KEYS = ("dreb", "oreb", "pf", "stl", "tov", "ast", "blk")


def validate_game(game: dict, box: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one parsed game. Errors keep it out of the output."""
    errs, warns = [], []
    teams = box["teams"]
    if len(teams) != 2:
        return [f"expected 2 box tables, found {len(teams)}"], []
    sides = (game["home"], game["away"])
    for side, t in zip(sides, teams):
        tag = t["team_id"]
        if t["team_id"] != side["team_id"]:
            errs.append(f"team order: box {t['team_id']} != results {side['team_id']}")
        if not t["players"]:
            errs.append(f"{tag}: no player rows")
            continue
        if t["total"] is None:
            errs.append(f"{tag}: no Total row")
            continue
        tr = t["team_row"] or {}
        s = sum(p["pts"] for p in t["players"]) + tr.get("pts", 0)
        if s != t["total"]["pts"]:
            errs.append(f"{tag}: sum pts {s} != Total {t['total']['pts']}")
        if tr.get("pts"):
            warns.append(f"{tag}: {tr['pts']} pts credited to the Team row, not a player (source)")
        for k in _SOFT_SUM_KEYS:
            s = sum(p[k] for p in t["players"]) + tr.get(k, 0)
            if s != t["total"][k]:
                warns.append(f"{tag}: sum {k} {s} != Total {t['total'][k]} (source)")
        for k in ("fg2", "fg3", "ft"):
            for i, name in ((0, "made"), (1, "att")):
                s = sum(p[k][i] for p in t["players"]) + (tr.get(k) or [0, 0])[i]
                if s != t["total"][k][i]:
                    errs.append(f"{tag}: sum {k} {name} {s} != Total {t['total'][k][i]}")
        for p in t["players"]:
            for k in ("fg2", "fg3", "ft"):
                if p[k][0] > p[k][1]:
                    errs.append(f"{tag}: player {p['id']} {k} made > att")
        if t["total"]["pts"] != side["pts"]:
            errs.append(f"{tag}: Total pts {t['total']['pts']} != score {side['pts']}")
        if len(t["q"]) != 4 + game["ot"]:
            errs.append(f"{tag}: {len(t['q'])} periods, expected {4 + game['ot']} (ot={game['ot']})")
        if sum(t["q"]) != side["pts"]:
            errs.append(f"{tag}: sum(q) {sum(t['q'])} != score {side['pts']}")
        # players' minutes, not the Total row (which is stale in some OT games)
        mins = sum(p["min"] for p in t["players"])
        expect = 200 + 25 * game["ot"]
        if abs(mins - expect) > 5:
            warns.append(f"{tag}: team minutes {mins}, expected ~{expect} (partial game?)")
    return errs, warns


# --------------------------------------------------------------------------- #
# output                                                                      #
# --------------------------------------------------------------------------- #
def box_doc(season: str, game: dict, box: dict) -> dict:
    teams = []
    for side_name, side, t in zip(("home", "away"), (game["home"], game["away"]), box["teams"]):
        tr = t["team_row"] or {}
        doc = {
            "side": side_name,
            "team_id": t["team_id"],
            "coach": t["coach"],
            "pts": side["pts"],
            "q": t["q"],
            # the site's "Team" row: team rebounds / turnovers, and occasionally
            # points the statisticians did not attribute to any player
            "team_row": {k: tr.get(k, 0 if k not in ("fg2", "fg3", "ft") else [0, 0])
                         for k in ("pts", "fg2", "fg3", "ft", "oreb", "dreb", "ast", "stl", "tov", "blk", "pf")},
            "players": t["players"],
        }
        if "more" in t:
            doc["more"] = t["more"]
        teams.append(doc)
    return {
        "schema_version": SCHEMA_VERSION,
        "id": game["id"],
        "season": season,
        "stage": game["stage"],
        "round": game["round"],
        "date": game["date"],
        "time": game["time"],
        "venue": game["venue"],
        "ot": game["ot"],
        "referees": box["referees"],
        "attendance": box["attendance"],
        **({"flags": game["flags"]} if game.get("flags") else {}),
        "teams": teams,
    }


def log_rows(game: dict, box: dict) -> list[list]:
    rows = []
    ids = (game["home"]["team_id"], game["away"]["team_id"])
    for i, t in enumerate(box["teams"]):
        for p in t["players"]:
            if p["min"] == 0 and not any(
                p[k] for k in ("pts", "dreb", "oreb", "ast", "stl", "tov", "blk", "pf")
            ):
                continue  # dressed, did not play
            rows.append([
                game["id"], p["id"], ids[i], ids[1 - i], 1 if i == 0 else 0,
                1 if p["starter"] else 0, p["min"], p["pts"],
                p["fg2"][0], p["fg2"][1], p["fg3"][0], p["fg3"][1], p["ft"][0], p["ft"][1],
                p["oreb"], p["dreb"], p["ast"], p["stl"], p["tov"], p["blk"],
                p["pf"], p["fd"], p["pir"], p["pm"],
            ])
    return rows


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# player identity                                                             #
# --------------------------------------------------------------------------- #
# The site issues a NEW PlayerId each time a player changes team mid-season;
# data.json (via the ingest identity map) keeps one canonical id per player
# with combined season totals. Box-score rows are mapped onto that id by exact
# (normalised) name when the name is unique in the season; the site's id is
# kept as `src_id`. Players data.json does not know at all keep their site id.
def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def load_identity(season: str) -> tuple[set[int], dict[str, int]]:
    try:
        players = json.loads(DATA_JSON.read_text(encoding="utf-8"))["seasons"][season]["players"]
    except (OSError, KeyError, ValueError):
        return set(), {}
    known = {int(p["id"]) for p in players}
    by_name: dict[str, set[int]] = {}
    for p in players:
        by_name.setdefault(_norm_name(p.get("name")), set()).add(int(p["id"]))
    return known, {n: next(iter(ids)) for n, ids in by_name.items() if n and len(ids) == 1}


def map_identity(box: dict, known: set[int], by_name: dict[str, int], stats: dict) -> None:
    for t in box["teams"]:
        for p in t["players"]:
            if p["id"] in known:
                continue
            canon = by_name.get(_norm_name(p["name"]))
            if canon is not None:
                p["src_id"], p["id"] = p["id"], canon
                stats["mapped"].add((p["src_id"], canon, p["name"]))
            else:
                stats["unknown"].add((p["id"], p["name"]))


# --------------------------------------------------------------------------- #
# cross-check against data.json (season totals)                               #
# --------------------------------------------------------------------------- #
def reconcile(season: str, logs: list[list], stage_of: dict[int, str]) -> dict:
    """Sum regular-season log rows per player and compare with data.json."""
    try:
        data = json.loads(DATA_JSON.read_text(encoding="utf-8"))["seasons"][season]
    except (OSError, KeyError, ValueError):
        return {"skipped": "data.json / season not available"}
    c = {name: i for i, name in enumerate(LOG_COLS)}
    agg: dict[int, dict] = {}
    for r in logs:
        if stage_of.get(r[c["game_id"]]) != "regular":
            continue
        a = agg.setdefault(r[c["player_id"]], {k: 0 for k in ("gp", "pts", "min", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast")})
        a["gp"] += 1
        a["pts"] += r[c["pts"]]
        a["min"] += r[c["min"]]
        a["fgm"] += r[c["fg2m"]] + r[c["fg3m"]]
        a["fga"] += r[c["fg2a"]] + r[c["fg3a"]]
        a["fg3m"] += r[c["fg3m"]]
        a["fg3a"] += r[c["fg3a"]]
        a["ftm"] += r[c["ftm"]]
        a["fta"] += r[c["fta"]]
        a["reb"] += r[c["oreb"]] + r[c["dreb"]]
        a["ast"] += r[c["ast"]]
    # data.json can list a mid-season transfer once per team: merge by player.
    season_tot: dict[int, dict] = {}
    for p in data["players"]:
        s = season_tot.setdefault(int(p["id"]), {k: 0 for k in ("gp", "pts", "min", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast")})
        for k in s:
            s[k] += p.get(k) or 0
    keys = list(next(iter(season_tot.values())).keys()) if season_tot else []
    exact, diffs = 0, []
    for pid, tot in season_tot.items():
        got = agg.get(pid)
        if got is None:
            if tot["gp"]:
                diffs.append((pid, "missing from logs", {}))
            continue
        d = {k: got[k] - tot[k] for k in keys if got[k] != tot[k]}
        if d:
            diffs.append((pid, "diff", d))
        else:
            exact += 1
    extra = sorted(set(agg) - set(season_tot))
    return {"players": len(season_tot), "exact": exact, "diffs": diffs, "not_in_data_json": extra}


# --------------------------------------------------------------------------- #
# main                                                                        #
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", required=True, help="YYYY-YYYY, e.g. 2025-2026")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="output root (default ./games)")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between network requests (min 1.0)")
    ap.add_argument("--offline", action="store_true", help="cache only; never touch the network")
    ap.add_argument("--limit", type=int, default=None, help="only fetch the first N played games (dev)")
    ap.add_argument("--game-ids", default="", help="comma list: only these games (dev / spot checks)")
    ap.add_argument("--check", action="store_true", help="parse + validate only; write nothing")
    args = ap.parse_args(argv)

    season = args.season.strip()
    cyear = season_to_cyear(season)
    fetch = CountingFetcher(max(args.delay, 1.0), args.cache_dir, args.offline)
    known_ids, id_by_name = load_identity(season)
    id_stats = {"mapped": set(), "unknown": set()}

    # 1) game list from every league board
    first = fetch.get("results.asp", {"cYear": cyear, "Board": REGULAR_BOARD}, label="results")
    games: list[dict] = []
    for stage, board in parse_boards(first):
        html = first if board == REGULAR_BOARD else fetch.get(
            "results.asp", {"cYear": cyear, "Board": board}, label=f"results {stage}")
        found = parse_results(html, stage)
        print(f"  board {board:>3} {stage:<13} {len(found):>4} games")
        games.extend(found)
    stage_of = {g["id"]: g["stage"] for g in games}

    played = [g for g in games if g["status"] == "final"]
    todo = played
    if args.game_ids:
        want = {int(x) for x in args.game_ids.split(",") if x.strip()}
        todo = [g for g in played if g["id"] in want]
    if args.limit is not None:
        todo = todo[: args.limit]

    # 2) box scores
    ok, bad, warned, no_box, logs = [], [], [], [], []
    out = args.out / season
    for n, g in enumerate(todo, 1):
        try:
            html = fetch.get("game-zone.asp", {"GameId": g["id"]}, label=f"game {g['id']}")
        except CacheMiss as exc:
            bad.append((g["id"], [str(exc)]))
            continue
        box = parse_box_score(html)
        if not box["teams"]:
            g["note"] = "no box score published"
            no_box.append(g["id"])
            continue
        errs, warns = validate_game(g, box)
        if errs:
            bad.append((g["id"], errs))
            continue
        if warns:
            g["flags"] = warns
            warned.append((g["id"], warns))
        map_identity(box, known_ids, id_by_name, id_stats)
        # the box page is the more precise source for the quarter line
        g["home"]["q"], g["away"]["q"] = box["teams"][0]["q"], box["teams"][1]["q"]
        g["attendance"] = box["attendance"]
        ok.append(g["id"])
        logs.extend(log_rows(g, box))
        if not args.check:
            _write_json(out / "g" / f"{g['id']}.json", box_doc(season, g, box))
        if n % 25 == 0:
            print(f"  .. {n}/{len(todo)} games")

    # 3) index + player logs
    bad_ids = {gid for gid, _ in bad}
    index_games = []
    for g in games:
        e = {k: g[k] for k in ("id", "stage", "round", "date", "time", "venue", "status", "ot")}
        e["attendance"] = g.get("attendance")
        e["home"] = {k: g["home"].get(k) for k in ("team_id", "pts", "q")}
        e["away"] = {k: g["away"].get(k) for k in ("team_id", "pts", "q")}
        e["box"] = g["id"] in ok and g["id"] not in bad_ids
        if g.get("flags"):
            e["flags"] = g["flags"]
        if g.get("note"):
            e["note"] = g["note"]
        index_games.append(e)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.check:
        _write_json(out / "index.json", {
            "schema_version": SCHEMA_VERSION, "season": season, "generated_at": now,
            "games": index_games,
        })
        _write_json(out / "player_logs.json", {
            "schema_version": SCHEMA_VERSION, "season": season, "generated_at": now,
            "cols": LOG_COLS, "rows": logs,
        })
        # games/seasons.json: which seasons have game data. The dashboard reads
        # this first so it never requests (and 404s on) a season without games.
        manifest_path = args.out / "seasons.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        seasons = manifest.get("seasons", {})
        seasons[season] = {"generated_at": now, "games": len(ok)}
        _write_json(manifest_path, {"schema_version": SCHEMA_VERSION,
                                    "seasons": dict(sorted(seasons.items()))})

    # 4) report
    print()
    print(f"season {season}: {len(games)} fixtures, {len(played)} played, "
          f"{len(todo)} attempted -> {len(ok)} ok, {len(bad)} failed")
    print(f"requests: {fetch.hits} from cache, {fetch.fetched} from network"
          f"{' (offline)' if args.offline else ''}")
    ot_games = [g for g in todo if g["ot"] and g["id"] in ok]
    if ot_games:
        print("overtime games validated: " + ", ".join(f"{g['id']} ({g['ot']}OT)" for g in ot_games))
    for gid, errs in bad:
        print(f"  FAIL {gid}: " + "; ".join(errs[:4]))
    for gid, warns in warned:
        print(f"  warn {gid}: " + "; ".join(warns[:4]))
    for gid in no_box:
        print(f"  note {gid}: no box score published on the site (kept in index, box=false)")
    print(f"player-game rows: {len(logs)}")
    if id_stats["mapped"]:
        print(f"identity: {len(id_stats['mapped'])} transfer ids mapped to data.json by name: "
              + ", ".join(f"{n} {a}->{b}" for a, b, n in sorted(id_stats["mapped"], key=lambda x: x[2])))
    if id_stats["unknown"]:
        print(f"identity: {len(id_stats['unknown'])} players not in data.json (kept site id): "
              + ", ".join(f"{n} ({i})" for i, n in sorted(id_stats["unknown"], key=lambda x: x[1])))
    if not args.check:
        print(f"wrote {out}")

    full = not args.limit and not args.game_ids and len(ok) + len(no_box) == len(played)
    if full:
        rec = reconcile(season, logs, stage_of)
        if "skipped" in rec:
            print(f"reconciliation skipped: {rec['skipped']}")
        else:
            print(f"reconciliation vs data.json (regular season): {rec['exact']}/{rec['players']} "
                  f"players exact, {len(rec['diffs'])} differ, "
                  f"{len(rec['not_in_data_json'])} in logs but not in data.json")
            for pid, kind, d in rec["diffs"][:15]:
                print(f"  {pid}: {kind} {d}")
    else:
        print("reconciliation vs data.json: skipped (partial run)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
