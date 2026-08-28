#!/usr/bin/env python3
"""
check_data_quality.py -- standalone data-quality audit for the source
workbook (``data/Basketball_Analytics.xlsx``). No database required: it reads
the Excel sheets directly, so it can run before ``ingest.py`` and in CI.

Two independent checks
----------------------

1. **Field-goal / free-throw internal consistency** -- per player row and per
   team row:

   * ``FGM <= FGA`` and ``FTM <= FTA``
   * three-pointers are a subset of field goals: ``3PM <= FGM`` and
     ``3PA <= FGA`` (the known "3PA/3PM > FGA/FGM" spreadsheet bug -- see
     ``data/shooting_stat_investigation.md``)
   * the derived two-point split is sane: ``FGM - 3PM >= 0``,
     ``FGA - 3PA >= 0``, and ``2PM <= 2PA``
   * points reconcile with the shot split:
     ``PTS == 2*(FGM - 3PM) + 3*3PM + FTM`` -- this is what catches a
     FIBA/NBA-style **2PT vs 3PT mapping** mistake, where makes were bucketed
     into the wrong column
   * ``FG%`` / ``3P%`` / ``FT%`` re-derived from the make/attempt columns
     agree with the stored percentage column (within ``--pct-tolerance``)

2. **Aggregation check** -- for every team, the sum of its players' season
   totals (joined to a team through the ``Roster`` sheet) matches the
   ``Team_Stats`` row within a tolerance
   (``max(--abs-tolerance, --tolerance * team_value)``). Checked stats:
   PTS, FGM, FGA, 3PM, 3PA, FTM, FTA, AST, TOV, STL, BLK. ``GP``/``MIN``
   (not player-summable conventions), ``OREB``/``DREB``/``REB`` (box scores
   credit some rebounds to the team, not a player) and ``PIR`` (a composite)
   are excluded on purpose.

Note: run against the shipped ``data/Basketball_Analytics.xlsx`` this exits
non-zero -- there are documented Player_Stats-vs-Team_Stats scope mismatches
for a few clubs (see ``data/shooting_stat_investigation.md``). That's the
tool doing its job, not a script failure.

Exit code is non-zero if any check fails.

Usage
-----
    python scripts/check_data_quality.py
    python scripts/check_data_quality.py --competition playoffs
    python scripts/check_data_quality.py --tolerance 0.05 --abs-tolerance 5
    python scripts/check_data_quality.py --workbook path/to/file.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_WORKBOOK = Path(__file__).resolve().parents[1] / "data" / "Basketball_Analytics.xlsx"

# stored-percentage column -> (made column, attempted column)
PCT_TRIOS = [("FG%", "FGM", "FGA"), ("3P%", "3PM", "3PA"), ("FT%", "FTM", "FTA")]

# Counting stats expected to sum player-rows -> team-row. OREB/DREB/REB and
# PIR are deliberately excluded: box scores credit some rebounds to the team
# itself (missed-FT out of bounds, end-of-period), so team rebounds legitimately
# exceed the player sum, and PIR is a composite that doesn't re-add exactly.
SUM_STATS = ["PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA", "AST", "TOV", "STL", "BLK"]

# competition -> (team sheet, player sheet)
SHEET_SETS = {
    "regular_season": ("Team_Stats", "Player_Stats"),
    "playoffs": ("Team_Stats_Playoffs", "Player_Stats_Playoffs"),
}


# --------------------------------------------------------------------------- #
# check 1: per-row field-goal / free-throw consistency
# --------------------------------------------------------------------------- #
def check_fg_consistency(df: pd.DataFrame, id_col: str, scope: str,
                         pct_tol: float, pts_tol: float) -> list[dict]:
    problems: list[dict] = []

    def flag(rid, issue, detail):
        problems.append({"scope": scope, "id": rid, "issue": issue, "detail": detail})

    for _, r in df.iterrows():
        rid = r[id_col]
        fgm, fga = float(r["FGM"]), float(r["FGA"])
        tpm, tpa = float(r["3PM"]), float(r["3PA"])
        ftm, fta = float(r["FTM"]), float(r["FTA"])
        pts = float(r["PTS"])

        if fgm > fga:
            flag(rid, "FGM > FGA", f"{fgm:g} > {fga:g}")
        if ftm > fta:
            flag(rid, "FTM > FTA", f"{ftm:g} > {fta:g}")
        if tpm > fgm:
            flag(rid, "3PM > FGM (3s not a subset of FGs)", f"{tpm:g} > {fgm:g}")
        if tpa > fga:
            flag(rid, "3PA > FGA (3s not a subset of FGs)", f"{tpa:g} > {fga:g}")

        two_pm, two_pa = fgm - tpm, fga - tpa
        if two_pm < 0:
            flag(rid, "derived 2PM negative", f"FGM - 3PM = {two_pm:g}")
        if two_pa < 0:
            flag(rid, "derived 2PA negative", f"FGA - 3PA = {two_pa:g}")
        if two_pm > two_pa >= 0:
            flag(rid, "derived 2PM > 2PA", f"{two_pm:g} > {two_pa:g}")

        expected_pts = 2 * (fgm - tpm) + 3 * tpm + ftm
        if abs(expected_pts - pts) > pts_tol:
            flag(rid, "PTS != 2*(FGM-3PM) + 3*3PM + FTM",
                 f"stored {pts:g}, implied {expected_pts:g} (diff {pts - expected_pts:+g})")

        for pct_col, m_col, a_col in PCT_TRIOS:
            made, att = float(r[m_col]), float(r[a_col])
            derived = (made / att * 100.0) if att else 0.0
            stored = r[pct_col]
            if pd.notna(stored) and abs(derived - float(stored)) > pct_tol:
                flag(rid, f"{pct_col} disagrees with {m_col}/{a_col}",
                     f"stored {float(stored):g}, derived {derived:.2f}")

    return problems


# --------------------------------------------------------------------------- #
# check 2: player totals vs team totals
# --------------------------------------------------------------------------- #
def check_aggregation(team_df: pd.DataFrame, player_df: pd.DataFrame,
                      roster: pd.DataFrame, tol: float, abs_tol: float) -> pd.DataFrame:
    joined = player_df.merge(roster[["PlayerId", "TeamID"]], on="PlayerId", how="left")
    missing = joined["TeamID"].isna().sum()
    if missing:
        print(f"  note: {missing} player row(s) had no Roster/team match and were dropped "
              "from the aggregation check")
        joined = joined.dropna(subset=["TeamID"])

    player_sums = joined.groupby("TeamID")[SUM_STATS].sum()
    team_vals = team_df.set_index("TeamId")[SUM_STATS]

    rows = []
    for team_id in sorted(team_vals.index):
        for stat in SUM_STATS:
            tv = float(team_vals.at[team_id, stat])
            ps = float(player_sums.at[team_id, stat]) if team_id in player_sums.index else 0.0
            diff = ps - tv
            allowed = max(abs_tol, tol * abs(tv))
            rows.append({
                "team": team_id, "stat": stat,
                "player_sum": round(ps, 1), "team_value": round(tv, 1),
                "diff": round(diff, 1),
                "pct": round((diff / tv * 100.0) if tv else 0.0, 2),
                "ok": abs(diff) <= allowed,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
def run_competition(xls: pd.ExcelFile, competition: str, roster: pd.DataFrame,
                    args: argparse.Namespace) -> tuple[bool, bool]:
    """Returns (fg_ok, aggregation_ok) for this competition."""
    team_sheet, player_sheet = SHEET_SETS[competition]
    if team_sheet not in xls.sheet_names or player_sheet not in xls.sheet_names:
        print(f"\n== {competition}: sheets not present ({team_sheet} / {player_sheet}) -- skipped")
        return True

    team_df = pd.read_excel(xls, team_sheet)
    player_df = pd.read_excel(xls, player_sheet)
    print(f"\n{'=' * 72}\n{competition}  --  {len(player_df)} player rows, {len(team_df)} team rows\n{'=' * 72}")

    # ---- check 1 ----
    problems = (
        check_fg_consistency(player_df, "PlayerId", "player", args.pct_tolerance, args.pts_tolerance)
        + check_fg_consistency(team_df, "TeamId", "team", args.pct_tolerance, args.pts_tolerance)
    )
    print(f"\n[1] Field-goal / free-throw consistency: "
          f"{len(problems)} issue(s) across {len(player_df) + len(team_df)} rows")
    if problems:
        pdf = pd.DataFrame(problems)
        with pd.option_context("display.max_rows", None, "display.width", 200):
            print(pdf.to_string(index=False))

    # ---- check 2 ----
    agg = check_aggregation(team_df, player_df, roster, args.tolerance, args.abs_tolerance)
    fails = agg[~agg["ok"]]
    print(f"\n[2] Player totals vs team totals "
          f"(tolerance: max({args.abs_tolerance:g}, {args.tolerance:.0%} of team value)): "
          f"{len(fails)} mismatch(es) of {len(agg)} checks")
    if not fails.empty:
        with pd.option_context("display.max_rows", None, "display.width", 200):
            print(fails.drop(columns="ok").to_string(index=False))

    league = (
        agg.groupby("stat", sort=False)[["player_sum", "team_value", "diff"]].sum().reset_index()
    )
    league["pct"] = (league["diff"] / league["team_value"].replace(0, pd.NA) * 100).round(2)
    print("\n    league-wide totals (all teams summed):")
    print(league.to_string(index=False))

    return (not problems, fails.empty)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK,
                    help=f"path to the source .xlsx (default: {DEFAULT_WORKBOOK})")
    ap.add_argument("--competition", choices=["regular_season", "playoffs", "both"], default="both")
    ap.add_argument("--tolerance", type=float, default=0.02,
                    help="relative tolerance for the aggregation check (default: 0.02 = 2%%)")
    ap.add_argument("--abs-tolerance", type=float, default=3.0,
                    help="absolute floor for the aggregation tolerance (default: 3)")
    ap.add_argument("--pct-tolerance", type=float, default=1.5,
                    help="max allowed gap between stored and derived FG%%/3P%%/FT%% (default: 1.5)")
    ap.add_argument("--pts-tolerance", type=float, default=2.0,
                    help="max allowed gap in the PTS reconciliation (default: 2.0 -- the source "
                         "PTS column has occasional +/-1 rounding vs the reconstructed shot split; "
                         "a real 2PT/3PT mapping error shows up as a larger, consistent gap)")
    ap.add_argument("--fail-on", choices=["any", "fg", "none"], default="any",
                    help="which findings set a non-zero exit code: 'any' (default) = either check, "
                         "'fg' = only the impossible-row check, 'none' = report only")
    args = ap.parse_args()

    if not args.workbook.exists():
        print(f"error: workbook not found: {args.workbook}", file=sys.stderr)
        return 2

    xls = pd.ExcelFile(args.workbook)
    if "Roster" not in xls.sheet_names:
        print("error: workbook has no 'Roster' sheet -- cannot run the aggregation check", file=sys.stderr)
        return 2
    roster = pd.read_excel(xls, "Roster")

    competitions = ["regular_season", "playoffs"] if args.competition == "both" else [args.competition]
    outcomes = [run_competition(xls, c, roster, args) for c in competitions]
    fg_ok = all(o[0] for o in outcomes)
    agg_ok = all(o[1] for o in outcomes)

    print(f"\n{'=' * 72}")
    print(f"RESULT: field-goal consistency = {'PASS' if fg_ok else 'FAIL'}, "
          f"aggregation = {'PASS' if agg_ok else 'FAIL'}")
    if args.fail_on == "none":
        return 0
    if args.fail_on == "fg":
        return 0 if fg_ok else 1
    return 0 if (fg_ok and agg_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
