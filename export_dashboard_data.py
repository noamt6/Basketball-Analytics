"""
Regenerate the dashboard's data file (``data.json``) from PostgreSQL.

``dashboard.html`` fetches ``./data.json`` at runtime; this script is what
produces it. It replaces the old workflow of hand-pasting a ``const DATA``
blob into the HTML.

Output shape (season-keyed so more seasons can be added without touching the
dashboard's loader)::

    {
      "default_season": "2023-2024",
      "seasons": {
        "2023-2024": {
          "season", "teams"[], "players"[], "by_position"[], "transfers"[],
          "bad_split_count", "player_count",
          "playoffs": { "teams"[], "players"[], "by_position"[], "bad_split_count" }
        }
      }
    }

Most fields are derived straight from the DB via ``metrics.py`` (so the
numbers track ``test_analytics.py``). A few are NOT in the database and are
read from ``dashboard_supplement.json``:

  * ``team.rank`` — the real league standing (not in the source workbook).
  * player/row display order — the dashboard lists rows in source-spreadsheet
    order, which the DB doesn't preserve; ``player_row_order`` restores it.
  * ``age_as_of`` — the date player ages are computed against.

Canonical ``efficiency`` is ``metrics.efficiency_index`` —
``(PTS+REB+AST+STL+BLK) - (missedFG + missedFT + TOV)`` — and that is the
default (``--efficiency-includes-tov``). The pre-existing hand-built
``data.json`` used a variant that omits the turnover term; pass
``--no-efficiency-includes-tov`` to reproduce that legacy value.

Usage::

    python export_dashboard_data.py                       # -> ./data.json
    python export_dashboard_data.py --out out/data.json --season 2023-2024
    python export_dashboard_data.py --check data.json     # diff DB export vs a reference file
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

import metrics
from db_client import get_engine

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "data.json"
SUPPLEMENT_PATH = HERE / "dashboard_supplement.json"
HEBREW_PATH = HERE / "data" / "hebrew_names.json"

PLAYER_SQL = """
    SELECT p.player_id, p.first_name, p.last_name, p.nationality, p.birth_date, p.height_m,
           r.team_id, r.position, r.jersey_number, r.years_on_team,
           s.gp, s.min, s.pts, s.fgm, s.fga, s.fg_pct, s.fg3m, s.fg3a, s.fg3_pct,
           s.ftm, s.fta, s.ft_pct, s.oreb, s.dreb, s.reb, s.ast, s.tov, s.stl, s.blk, s.pir
    FROM player_season_stats s
    JOIN players p ON p.player_id = s.player_id
    JOIN roster  r ON r.player_id = s.player_id AND r.season = s.season
    WHERE s.season = %(season)s AND s.competition = %(competition)s
"""

TEAM_SQL = """
    SELECT t.team_id, t.team_name, t.city,
           s.gp, s.min, s.pts, s.fgm, s.fga, s.fg_pct, s.fg3m, s.fg3a, s.fg3_pct,
           s.ftm, s.fta, s.ft_pct, s.oreb, s.dreb, s.reb, s.ast, s.tov, s.stl, s.blk, s.pir
    FROM team_season_stats s
    JOIN teams t ON t.team_id = s.team_id
    WHERE s.season = %(season)s AND s.competition = %(competition)s
"""

TRANSFER_SQL = """
    SELECT player_id, player_name, team_id_a, gp_a, team_id_b, gp_b, note
    FROM player_transfers
    WHERE season = %(season)s
    ORDER BY id
"""


def _num(value) -> float:
    """value -> float, with None/NaN/non-numeric collapsing to 0.0. DB NULLs
    come back as NaN via pandas, and JSON has no NaN, so every numeric field
    must pass through here or _r()."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _r(value, ndigits):
    """_num() then round."""
    return round(_num(value), ndigits)


def _pct(value):
    """Shooting percentage: 1 dp (how the dashboard displays it), but keep a
    genuine NULL as None so the UI shows '—' for a shot type never attempted."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _age(birth_date, as_of: date) -> int:
    if birth_date is None or (isinstance(birth_date, float) and math.isnan(birth_date)):
        return 0
    if isinstance(birth_date, str):
        birth_date = date.fromisoformat(birth_date[:10])
    if hasattr(birth_date, "date"):
        birth_date = birth_date.date()
    return as_of.year - birth_date.year - ((as_of.month, as_of.day) < (birth_date.month, birth_date.day))


def _efficiency(row, include_tov: bool):
    base = _num(row["pts"]) + _num(row["reb"]) + _num(row["ast"]) + _num(row["stl"]) + _num(row["blk"])
    misses = (_num(row["fga"]) - _num(row["fgm"])) + (_num(row["fta"]) - _num(row["ftm"]))
    if include_tov:
        misses += _num(row["tov"])
    return float(base - misses)


def _rank_by(pids, value_of, tiebreak_of) -> dict:
    """player_id -> 1-based rank, highest value first, ties broken by
    `tiebreak_of` ascending (spreadsheet row order)."""
    ordered = sorted(pids, key=lambda pid: (-value_of(pid), tiebreak_of(pid)))
    return {pid: i + 1 for i, pid in enumerate(ordered)}


def build_players(df: pd.DataFrame, *, hebrew: dict, he_by_name: dict, as_of: date,
                  include_tov: bool, order_index: dict) -> list[dict]:
    if df.empty:
        return []
    df = df.copy()
    pg = metrics.player_per_game_stats(df)

    # Ranks are by PIR *per game*, rounded to the displayed 2 dp, ties broken by
    # source row order — matches the dashboard's "#N in the league" convention.
    avg_pir = {int(r.player_id): round(_num(r.pir) / r.gp, 2) if r.gp else 0.0
               for r in df.itertuples()}
    team_of = {int(r.player_id): r.team_id for r in df.itertuples()}
    tb = lambda pid: order_index.get((team_of[pid], pid), 10_000 + pid)

    league_pir_rank = _rank_by(avg_pir.keys(), avg_pir.get, tb)
    team_pir_rank: dict = {}
    for team_id, grp in df.groupby("team_id"):
        pids = [int(x) for x in grp["player_id"]]
        team_pir_rank.update(_rank_by(pids, avg_pir.get, tb))

    out = []
    for _, row in pg.iterrows():
        pid = int(row["player_id"])
        bad_split = bool(row["fg3a"] > row["fga"] or row["fg3m"] > row["fgm"])
        out.append({
            "id": pid,
            "name": f"{row['first_name']} {row['last_name']}".strip(),
            "team_id": row["team_id"],
            "position": row["position"],
            "jersey": int(row["jersey_number"]) if pd.notna(row["jersey_number"]) else None,
            "years_on_team": int(row["years_on_team"]) if pd.notna(row["years_on_team"]) else None,
            "nationality": row["nationality"] or "",
            "age": _age(row["birth_date"], as_of),
            "height_m": _r(row["height_m"], 2),
            "gp": int(_num(row["gp"])),
            "avg_points": _r(row["avg_points"], 2),
            "avg_rebounds": _r(row["avg_rebounds"], 2),
            "avg_assists": _r(row["avg_assists"], 2),
            "avg_minutes": _r(row["avg_minutes"], 2),
            "avg_pir": _r(row["pir"] / row["gp"] if row["gp"] else 0, 2),
            "per_36_points": _r(row["per_36_points"], 2),
            "per_36_assists": _r(row["per_36_assists"], 2),
            "per_36_rebounds": _r(row["per_36_rebounds"], 2),
            "fg_pct": _pct(row["fg_pct"]),
            "fg3_pct": _pct(row["fg3_pct"]),
            "ft_pct": _pct(row["ft_pct"]),
            "efg_pct": _pct(row["efg_pct"]),
            "ts_pct": _pct(row["ts_pct"]),
            "ast_to_tov": _r(row["ast_to_tov"], 2),
            "efficiency": _efficiency(row, include_tov),
            "pir": int(_num(row["pir"])),
            "bad_split": bad_split,
            "pir_rank_on_team": team_pir_rank.get(pid, 0),
            "pir_rank_league": league_pir_rank.get(pid, 0),
            "name_he": (hebrew.get("players", {}).get(str(pid))
                        or he_by_name.get(f"{row['first_name']} {row['last_name']}".strip(), "")),
            "pts": int(_num(row["pts"])),
            "reb": int(_num(row["reb"])),
            "ast": int(_num(row["ast"])),
            "per_36_pir": _r(metrics.per_36(row["pir"], row["min"]), 2),
        })

    out.sort(key=lambda p: order_index.get((p["team_id"], p["id"]), 10_000 + p["id"]))
    return out


def build_teams(df: pd.DataFrame, *, hebrew: dict, rank_map: dict, roster_counts: dict) -> list[dict]:
    if df.empty:
        return []
    pg = metrics.team_per_game_stats(df.copy())
    he_teams = hebrew.get("teams", {})
    out = []
    for _, row in pg.iterrows():
        tid = row["team_id"]
        name, city = row["team_name"], row["city"] or ""
        label = f"{name} {city}".strip()
        he = he_teams.get(tid, {})
        out.append({
            "id": tid,
            "name": name,
            "city": city,
            "label": label,
            "rank": rank_map.get(tid, 0),
            "gp": int(_num(row["gp"])),
            "avg_points": _r(row["avg_points"], 2),
            "avg_assists": _r(row["avg_assists"], 2),
            "avg_rebounds": _r(row["avg_rebounds"], 2),
            "avg_blocks": _r(row["avg_blocks"], 2),
            "avg_turnovers": _r(row["avg_turnovers"], 2),
            "avg_pir": _r(row["avg_pir"], 2),
            "avg_oreb": _r(row["avg_oreb"], 2),
            "avg_dreb": _r(row["avg_dreb"], 2),
            "avg_fg3a": _r(row["avg_fg3a"], 2),
            "avg_fg3m": _r(row["avg_fg3m"], 2),
            "fg3_pct": _pct(row["fg3_pct"]),
            "player_count": roster_counts.get(tid, 0),
            "name_he": he.get("name_he", ""),
            "city_he": he.get("city_he", ""),
            "label_he": he.get("label_he", ""),
        })
    out.sort(key=lambda t: t["rank"] or 999)
    return out


def build_by_position(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    bp = metrics.performance_by_position(df.copy())
    return [
        {
            "position": r["position"],
            "avg_points": _r(r["avg_points"], 2),
            "avg_rebounds": _r(r["avg_rebounds"], 2),
            "avg_assists": _r(r["avg_assists"], 2),
        }
        for _, r in bp.iterrows()
    ]


def build_transfers(engine, season: str, *, teams_by_id: dict, name_to_pid: dict,
                    hebrew: dict, he_by_name: dict) -> list[dict]:
    df = pd.read_sql(TRANSFER_SQL, engine, params={"season": season})
    he_players = hebrew.get("players", {})
    out = []
    for _, row in df.iterrows():
        pid = row["player_id"]
        if pid is None or (isinstance(pid, float) and math.isnan(pid)):
            pid = name_to_pid.get(row["player_name"])
        name_he = (he_players.get(str(pid)) if pid is not None else "") \
            or he_by_name.get(row["player_name"], "")
        out.append({
            "player_name": row["player_name"],
            "team_a": row["team_id_a"],
            "team_a_label": teams_by_id.get(row["team_id_a"], row["team_id_a"]),
            "gp_a": int(row["gp_a"]) if pd.notna(row["gp_a"]) else 0,
            "team_b": row["team_id_b"],
            "team_b_label": teams_by_id.get(row["team_id_b"], row["team_id_b"]),
            "gp_b": int(row["gp_b"]) if pd.notna(row["gp_b"]) else 0,
            "note": row["note"] or "",
            "player_name_he": name_he,
        })
    return out


def build_season(engine, season: str, *, hebrew: dict, supplement: dict, include_tov: bool) -> dict:
    as_of = date.fromisoformat(supplement.get("age_as_of", f"{season[:4]}-06-30"))
    rank_map = supplement.get("team_rank", {})
    order_index = {(t, int(i)): n for n, (t, i) in enumerate(supplement.get("player_row_order", []))}

    reg_players = pd.read_sql(PLAYER_SQL, engine, params={"season": season, "competition": "regular_season"})
    reg_teams = pd.read_sql(TEAM_SQL, engine, params={"season": season, "competition": "regular_season"})
    po_players = pd.read_sql(PLAYER_SQL, engine, params={"season": season, "competition": "playoffs"})
    po_teams = pd.read_sql(TEAM_SQL, engine, params={"season": season, "competition": "playoffs"})

    teams_by_id = {r.team_id: f"{r.team_name} {r.city or ''}".strip() for r in reg_teams.itertuples()}
    name_to_pid = dict(zip(
        (reg_players["first_name"] + " " + reg_players["last_name"]).str.strip(),
        reg_players["player_id"],
    ))
    reg_roster_counts = reg_players.groupby("team_id")["player_id"].count().to_dict()
    po_roster_counts = po_players.groupby("team_id")["player_id"].count().to_dict()

    # name -> name_he, so a traded player whose surviving row carries the other
    # team's source id still resolves (hebrew_names.json is keyed by source id).
    he_players = hebrew.get("players", {})
    he_by_name = {}
    for r in reg_players.itertuples():
        he = he_players.get(str(int(r.player_id)))
        if he:
            he_by_name[f"{r.first_name} {r.last_name}".strip()] = he

    reg_p = build_players(reg_players, hebrew=hebrew, he_by_name=he_by_name, as_of=as_of,
                          include_tov=include_tov, order_index=order_index)
    po_p = build_players(po_players, hebrew=hebrew, he_by_name=he_by_name, as_of=as_of,
                         include_tov=include_tov, order_index=order_index)

    return {
        "season": season,
        "teams": build_teams(reg_teams, hebrew=hebrew, rank_map=rank_map, roster_counts=reg_roster_counts),
        "players": reg_p,
        "by_position": build_by_position(reg_players),
        "transfers": build_transfers(engine, season, teams_by_id=teams_by_id, name_to_pid=name_to_pid,
                                     hebrew=hebrew, he_by_name=he_by_name),
        "bad_split_count": sum(1 for p in reg_p if p["bad_split"]),
        "player_count": int(reg_players["player_id"].nunique()),
        "playoffs": {
            "teams": build_teams(po_teams, hebrew=hebrew, rank_map=rank_map, roster_counts=po_roster_counts),
            "players": po_p,
            "by_position": build_by_position(po_players),
            "bad_split_count": sum(1 for p in po_p if p["bad_split"]),
        },
    }


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def diff_json(a, b, path="") -> list[str]:
    """Structural diff — returns a list of human-readable mismatch lines."""
    out = []
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return [f"{path or '<root>'}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        for k in a.keys() | b.keys():
            if k not in a:
                out.append(f"{path}.{k}: missing on left")
            elif k not in b:
                out.append(f"{path}.{k}: missing on right")
            else:
                out += diff_json(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff_json(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        if abs(float(a) - float(b)) > 0.011:
            out.append(f"{path}: {a} != {b}")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output path (default: {DEFAULT_OUT})")
    parser.add_argument("--season", default="2023-2024", help="season to export (default: 2023-2024)")
    parser.add_argument("--efficiency-includes-tov", action=argparse.BooleanOptionalAction, default=True,
                        help="efficiency subtracts turnovers (metrics.efficiency_index). Default on; "
                             "--no-efficiency-includes-tov reproduces the legacy hand-built data.json value.")
    parser.add_argument("--check", type=Path, default=None,
                        help="don't write; diff the DB export against this reference json and print mismatches")
    parser.add_argument("--s3-uri", default=None,
                        help="after writing, also upload the file to this s3://bucket/key (used by the Fargate export task)")
    args = parser.parse_args()

    hebrew = _load_json(HEBREW_PATH, {})
    supplement = _load_json(SUPPLEMENT_PATH, {}).get(args.season, {})
    if not supplement:
        print(f"note: no dashboard_supplement.json entry for {args.season} — team.rank and row order will be unset.")

    engine = get_engine()
    season_blob = build_season(engine, args.season, hebrew=hebrew,
                               supplement=supplement, include_tov=args.efficiency_includes_tov)
    doc = {"default_season": args.season, "seasons": {args.season: season_blob}}

    if args.check:
        ref = _load_json(args.check, None)
        if ref is None:
            raise SystemExit(f"--check file not found: {args.check}")
        mismatches = diff_json(doc, ref, "")
        if not mismatches:
            print(f"MATCH — DB export is structurally equal to {args.check}")
            return
        print(f"{len(mismatches)} mismatch(es) vs {args.check}:")
        for line in mismatches[:200]:
            print("  " + line)
        if len(mismatches) > 200:
            print(f"  ... and {len(mismatches) - 200} more")
        raise SystemExit(1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.s3_uri:
        import boto3
        bucket, _, key = args.s3_uri.removeprefix("s3://").partition("/")
        boto3.client("s3").upload_file(
            str(args.out), bucket, key,
            ExtraArgs={"ContentType": "application/json", "CacheControl": "public,max-age=300"},
        )
        print(f"Uploaded to {args.s3_uri}")

    s = season_blob
    print(
        f"Wrote {args.out} — season {args.season}: {len(s['teams'])} teams, {len(s['players'])} players, "
        f"{len(s['transfers'])} transfers, {len(s['playoffs']['players'])} playoff players."
    )


if __name__ == "__main__":
    main()
