#!/usr/bin/env python3
"""
merge_game_totals.py -- fold per-game data (``games/``) back into ``data.json``
as season totals the season-totals feed never had.

WHY
---
``data.json`` comes from the league's season-totals tables: no wins/losses, no
points allowed, no steals, no +/-. ``scrape_games.py`` now has every game's
result and box score, so this pass derives those once, offline, and writes them
next to the existing fields -- the dashboard needs them at boot (League table,
Home leaders, skill radar) and must not fetch ``games/`` before a view asks for
it (``qa_audit_agent.js`` domain E guards that).

WHAT IT ADDS (regular season -> ``seasons[s]``; every non-regular stage, Play-In
included -> ``seasons[s].playoffs``, the same split ``scrape_games.reconcile``
uses)
  team   : w, l, home_w, home_l, away_w, away_l, pts_for, pts_against,
           avg_pts_against, avg_diff, streak ("W3" / "L1"), last5 ("WWLWL",
           oldest first) -- from every final result, box score or not;
           stl, avg_steals -- from box-score games only, over lg_gp of them
           (blocks already come with the season totals as avg_blocks).
  player : stl, blk, pf, fd, pm, starts, lg_gp, lg_min -- summed over the box
           scores the player appears in. Averages divide by lg_gp (not gp): a
           game without a published box score has no steals to count.
           jersey -- only where data.json has none: the number the player wore
           most often in the box scores (the season-totals feed and the roster
           widget miss ~25 % of shirt numbers; the box score prints them).
           Here 0 IS a shirt number (Lundberg, Bryant...): run this AFTER
           scrape_player_details.py, whose "jersey 0 -> null" cleanup treats the
           season-totals 0 as a missing-value sentinel.

Idempotent: every field is overwritten on each run. Seasons without
``games/<season>/`` are left untouched.

USAGE
-----
    python scripts/merge_game_totals.py              # patch data.json in place
    python scripts/merge_game_totals.py --dry-run    # report only
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYER_SUMS = ("stl", "blk", "pf", "fd", "pm", "starter", "min")


def _streak(results: list[str]) -> str:
    if not results:
        return ""
    last, n = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return f"{last}{n}"


def team_records(games: list[dict]) -> dict[str, dict]:
    """W/L, home/away split, points for/against and form from final results."""
    rec: dict[str, dict] = defaultdict(lambda: {
        "w": 0, "l": 0, "home_w": 0, "home_l": 0, "away_w": 0, "away_l": 0,
        "pts_for": 0, "pts_against": 0, "_res": []})
    ordered = sorted(games, key=lambda g: (g.get("date") or "", g.get("time") or "", g["id"]))
    for g in ordered:
        if g.get("status") != "final":
            continue
        h, a = g["home"], g["away"]
        for side, me, them in (("home", h, a), ("away", a, h)):
            r = rec[me["team_id"]]
            won = me["pts"] > them["pts"]
            r["w" if won else "l"] += 1
            r[f"{side}_{'w' if won else 'l'}"] += 1
            r["pts_for"] += me["pts"]
            r["pts_against"] += them["pts"]
            r["_res"].append("W" if won else "L")
    out = {}
    for tid, r in rec.items():
        gp = r["w"] + r["l"]
        res = r.pop("_res")
        r["avg_pts_against"] = round(r["pts_against"] / gp, 1) if gp else 0
        r["avg_diff"] = round((r["pts_for"] - r["pts_against"]) / gp, 1) if gp else 0
        r["streak"] = _streak(res)
        r["last5"] = "".join(res[-5:])
        out[tid] = r
    return out


def log_totals(logs: dict, keep) -> tuple[dict, dict]:
    """Per-player and per-team sums over the box-score rows `keep` accepts."""
    cols = logs["cols"]
    ix = {c: i for i, c in enumerate(cols)}
    players: dict[int, dict] = defaultdict(lambda: dict.fromkeys(PLAYER_SUMS, 0) | {"lg_gp": 0})
    teams: dict[str, dict] = defaultdict(lambda: {"stl": 0, "_games": set()})
    for row in logs["rows"]:
        if not keep(row[ix["game_id"]]):
            continue
        p = players[row[ix["player_id"]]]
        for k in PLAYER_SUMS:
            p[k] += row[ix[k]] or 0
        p["lg_gp"] += 1
        t = teams[row[ix["team_id"]]]
        t["stl"] += row[ix["stl"]] or 0
        t["_games"].add(row[ix["game_id"]])
    return players, teams


def patch_block(block: dict, records: dict, p_tot: dict, t_tot: dict) -> tuple[int, int]:
    n_t = n_p = 0
    for tm in block.get("teams", []):
        r = records.get(tm["id"])
        if r:
            tm.update(r)
            n_t += 1
        tt = t_tot.get(tm["id"])
        if tt:
            g = len(tt["_games"])
            tm.update({"stl": tt["stl"], "lg_gp": g,
                       "avg_steals": round(tt["stl"] / g, 1) if g else 0})
    for pl in block.get("players", []):
        s = p_tot.get(pl["id"])
        if not s:
            continue
        pl.update({"stl": s["stl"], "blk": s["blk"], "pf": s["pf"], "fd": s["fd"],
                   "pm": s["pm"], "starts": s["starter"], "lg_gp": s["lg_gp"],
                   "lg_min": s["min"]})
        n_p += 1
    return n_t, n_p


def box_jerseys(gdir: Path) -> dict[int, int]:
    """Most-worn shirt number per player id across the season's box scores."""
    seen: dict[int, Counter] = defaultdict(Counter)
    for fp in (gdir / "g").glob("*.json"):
        box = json.loads(fp.read_text(encoding="utf-8"))
        for tm in box.get("teams", []):
            for p in tm.get("players", []):
                # 0 is a real shirt number here (the box score always prints one)
                if p.get("id") is not None and p.get("jersey") is not None:
                    seen[p["id"]][p["jersey"]] += 1
    return {pid: c.most_common(1)[0][0] for pid, c in seen.items()}


def fill_jerseys(block: dict, jerseys: dict[int, int]) -> int:
    """Only fills holes -- a roster-widget number from scrape_player_details wins."""
    n = 0
    for pl in block.get("players", []):
        if pl.get("jersey") is None and pl["id"] in jerseys:
            pl["jersey"] = jerseys[pl["id"]]
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data.json")
    ap.add_argument("--games", type=Path, default=ROOT / "games")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    doc = json.loads(args.data.read_text(encoding="utf-8"))
    for season, blob in sorted(doc["seasons"].items()):
        gdir = args.games / season
        if not (gdir / "index.json").exists() or not (gdir / "player_logs.json").exists():
            print(f"{season}: no games/ data, skipped")
            continue
        idx = json.loads((gdir / "index.json").read_text(encoding="utf-8"))
        logs = json.loads((gdir / "player_logs.json").read_text(encoding="utf-8"))
        stage = {g["id"]: g["stage"] for g in idx["games"]}
        jerseys = box_jerseys(gdir)
        for comp, block in (("regular", blob), ("playoffs", blob.get("playoffs"))):
            if not block:
                continue
            is_reg = comp == "regular"
            games = [g for g in idx["games"] if (g["stage"] == "regular") == is_reg]
            p_tot, t_tot = log_totals(logs, lambda gid: (stage.get(gid) == "regular") == is_reg)
            n_t, n_p = patch_block(block, team_records(games), p_tot, t_tot)
            n_j = fill_jerseys(block, jerseys)
            missing = [pl["id"] for pl in block.get("players", []) if pl["id"] not in p_tot]
            print(f"{season} {comp:8s}: {n_t}/{len(block.get('teams', []))} teams, "
                  f"{n_p}/{len(block.get('players', []))} players"
                  + (f" ({len(missing)} without box-score rows)" if missing else "")
                  + (f", {n_j} jerseys filled" if n_j else ""))
    if args.dry_run:
        print("dry run -- data.json not written")
        return 0
    with open(args.data, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {args.data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
