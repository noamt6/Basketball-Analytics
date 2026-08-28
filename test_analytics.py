"""
Sanity-check runner: queries the database, computes metrics via metrics.py,
and prints leaderboards. Not a pytest suite — a script meant to be read
while comparing its output against data/VIEWS.xlsx (which holds the same
numbers pre-computed in Excel) to confirm the pipeline is correct.

Run after `python ingest.py`:
    python test_analytics.py

Defaults to the regular season (matches data/VIEWS.xlsx, which is
regular-season only). To see the playoffs instead (only 8 of 13 teams
qualified):
    COMPETITION=playoffs python test_analytics.py
"""
from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import text

from db_client import get_engine
import metrics

pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
SEASON = os.getenv("SEASON", "2023-2024")
# 'regular_season' (default, ~29-30 GP, all 13 teams) or 'playoffs' (8 teams
# who qualified). These are two stages of the same Winner League competition.
COMPETITION = os.getenv("COMPETITION", "regular_season")

PLAYER_QUERY = text("""
    SELECT
        p.player_id, p.first_name || ' ' || p.last_name AS player_name,
        r.position, r.years_on_team, r.team_id,
        s.gp, s.min, s.pts, s.fgm, s.fga, s.fg3m, s.fg3a,
        s.ftm, s.fta, s.oreb, s.dreb, s.reb, s.ast, s.tov, s.stl, s.blk, s.pir
    FROM player_season_stats s
    JOIN players p ON p.player_id = s.player_id
    JOIN roster r ON r.player_id = s.player_id AND r.season = s.season
    WHERE s.season = :season AND s.competition = :competition
""")

TEAM_QUERY = text("""
    SELECT
        t.team_id, t.team_name,
        s.gp, s.min, s.pts, s.fgm, s.fga, s.fg3m, s.fg3a,
        s.ftm, s.fta, s.oreb, s.dreb, s.reb, s.ast, s.tov, s.stl, s.blk, s.pir
    FROM team_season_stats s
    JOIN teams t ON t.team_id = s.team_id
    WHERE s.season = :season AND s.competition = :competition
""")


def _print_top(df: pd.DataFrame, columns: list[str], sort_by: str, title: str, n: int = 5) -> None:
    print(f"\n--- {title} ---")
    print(df.sort_values(sort_by, ascending=False)[columns].head(n).to_string(index=False))


def main() -> None:
    engine = get_engine()
    players = pd.read_sql(PLAYER_QUERY, engine, params={"season": SEASON, "competition": COMPETITION})
    teams = pd.read_sql(TEAM_QUERY, engine, params={"season": SEASON, "competition": COMPETITION})

    if players.empty or teams.empty:
        print(
            f"No data found for season={SEASON!r} competition={COMPETITION!r}. "
            "Run `python ingest.py` first, or set COMPETITION=regular_season "
            "(only 8 of 13 teams have playoffs rows)."
        )
        return

    player_stats = metrics.player_per_game_stats(players)
    team_stats = metrics.team_per_game_stats(teams)

    print(f"Season: {SEASON}  |  competition: {COMPETITION}  |  {len(players)} players, {len(teams)} teams")

    _print_top(player_stats, ["player_name", "avg_points"], "avg_points", "Top scorers (avg points/game)")
    _print_top(player_stats, ["player_name", "efg_pct", "ts_pct"], "ts_pct", "Most efficient shooters (TS%)")
    _print_top(player_stats, ["player_name", "ast_to_tov"], "ast_to_tov", "Best AST/TOV ratio")
    _print_top(player_stats, ["player_name", "per_36_points", "per_36_assists", "per_36_rebounds"],
               "per_36_points", "Per-36 leaders (points)")
    _print_top(player_stats, ["player_name", "efficiency"], "efficiency", "Top efficiency index (EFF)")

    _print_top(team_stats, ["team_name", "avg_points"], "avg_points", "Team offense (avg points/game)", n=len(team_stats))
    _print_top(team_stats, ["team_name", "avg_pir"], "avg_pir", "Team PIR leaders", n=len(team_stats))

    print("\n--- Avg points/rebounds/assists by position ---")
    print(metrics.performance_by_position(players).to_string(index=False))

    print("\n--- Avg points/rebounds/assists by years on team ---")
    print(metrics.performance_by_tenure(players).to_string(index=False))


if __name__ == "__main__":
    main()
