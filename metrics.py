"""
Basketball statistics — traditional and advanced.

Every scalar function accepts plain numbers OR pandas Series/numpy arrays
(they're built on numpy, which broadcasts either way) and is safe against
division by zero (returns 0 instead of raising / producing inf-NaN).

The DataFrame-level functions at the bottom replicate the analytical
views in data/VIEWS.xlsx (Position_Performance, Team_Stats_Comparison,
Per_36, Asists_To_Turnovers_Ratio, ...), computed from the raw season
totals stored in team_season_stats / player_season_stats instead of
being pre-baked in Excel.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(numerator, denominator):
    """Division that returns 0 (elementwise) wherever the denominator is 0,
    instead of raising or producing inf/NaN. Works for two scalars, two
    pandas Series, or a Series and a scalar."""
    if isinstance(numerator, pd.Series) or isinstance(denominator, pd.Series):
        num = numerator if isinstance(numerator, pd.Series) else pd.Series(numerator, index=denominator.index)
        den = denominator if isinstance(denominator, pd.Series) else pd.Series(denominator, index=numerator.index)
        return (num / den.replace(0, np.nan)).fillna(0.0)
    return float(numerator) / float(denominator) if denominator else 0.0


# ---------------------------------------------------------------------------
# Shooting percentages
# ---------------------------------------------------------------------------

def fg_pct(fgm, fga):
    """Field goal % (0-100 scale, matching the source data's convention)."""
    return _safe_div(fgm, fga) * 100


def fg3_pct(fg3m, fg3a):
    """Three-point % (0-100 scale)."""
    return _safe_div(fg3m, fg3a) * 100


def ft_pct(ftm, fta):
    """Free throw % (0-100 scale)."""
    return _safe_div(ftm, fta) * 100


def effective_fg_pct(fgm, fg3m, fga):
    """eFG% — field-goal % adjusted to give 3-pointers their extra value."""
    return _safe_div(fgm + 0.5 * fg3m, fga) * 100


def true_shooting_pct(pts, fga, fta):
    """TS% — scoring efficiency accounting for 2s, 3s, and free throws together."""
    return _safe_div(pts, 2 * (fga + 0.44 * fta)) * 100


# ---------------------------------------------------------------------------
# Efficiency / ball-handling
# ---------------------------------------------------------------------------

def ast_to_tov_ratio(ast, tov):
    """Assist-to-turnover ratio."""
    return _safe_div(ast, tov)


def efficiency_index(pts, reb, ast, stl, blk, fgm, fga, ftm, fta, tov):
    """
    Standard basketball "Efficiency" (EFF) composite:
        (PTS+REB+AST+STL+BLK) - ((FGA-FGM)+(FTA-FTM)+TOV)

    Note: this is used as our working definition of "Net Efficiency" from
    the original spec. A true net rating (offensive rating minus defensive
    rating per 100 possessions) needs opponent/possession data that isn't
    present in the season-totals dataset — revisit if play-by-play or
    opponent scoring data becomes available.
    """
    missed_fg = fga - fgm
    missed_ft = fta - ftm
    return (pts + reb + ast + stl + blk) - (missed_fg + missed_ft + tov)


# ---------------------------------------------------------------------------
# Rate stats
# ---------------------------------------------------------------------------

def per_game(stat_total, gp):
    """Convert a season total into a per-game average."""
    return _safe_div(stat_total, gp)


def per_36(stat_total, minutes_total):
    """Extrapolate a season total to a per-36-minutes rate."""
    return _safe_div(stat_total, minutes_total) * 36


# ---------------------------------------------------------------------------
# DataFrame-level views (mirror data/VIEWS.xlsx)
# ---------------------------------------------------------------------------

def player_per_game_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given player season totals (one row per player, columns: gp, min, pts,
    fgm, fga, fg3m, fg3a, ftm, fta, reb, oreb, dreb, ast, tov, stl, blk),
    return a copy with per-game, per-36, and advanced-metric columns added.
    """
    out = df.copy()
    out["avg_points"] = per_game(out["pts"], out["gp"])
    out["avg_rebounds"] = per_game(out["reb"], out["gp"])
    out["avg_assists"] = per_game(out["ast"], out["gp"])
    out["avg_minutes"] = per_game(out["min"], out["gp"])
    out["per_36_points"] = per_36(out["pts"], out["min"])
    out["per_36_assists"] = per_36(out["ast"], out["min"])
    out["per_36_rebounds"] = per_36(out["reb"], out["min"])
    out["efg_pct"] = effective_fg_pct(out["fgm"], out["fg3m"], out["fga"])
    out["ts_pct"] = true_shooting_pct(out["pts"], out["fga"], out["fta"])
    out["ast_to_tov"] = ast_to_tov_ratio(out["ast"], out["tov"])
    out["efficiency"] = efficiency_index(
        out["pts"], out["reb"], out["ast"], out["stl"], out["blk"],
        out["fgm"], out["fga"], out["ftm"], out["fta"], out["tov"],
    )
    return out


def team_per_game_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Team season totals -> per-game averages, mirroring VIEWS.xlsx's Team_Stats_Comparison."""
    out = df.copy()
    out["avg_points"] = per_game(out["pts"], out["gp"])
    out["avg_assists"] = per_game(out["ast"], out["gp"])
    out["avg_rebounds"] = per_game(out["reb"], out["gp"])
    out["avg_blocks"] = per_game(out["blk"], out["gp"])
    out["avg_turnovers"] = per_game(out["tov"], out["gp"])
    out["avg_pir"] = per_game(out["pir"], out["gp"])
    out["avg_oreb"] = per_game(out["oreb"], out["gp"])
    out["avg_dreb"] = per_game(out["dreb"], out["gp"])
    out["avg_fg3a"] = per_game(out["fg3a"], out["gp"])
    out["avg_fg3m"] = per_game(out["fg3m"], out["gp"])
    return out


def _season_aware_group(per_game_df: pd.DataFrame, key: str) -> list[str]:
    """Group by `key`, additionally splitting on `season` when the frame
    actually carries more than one season (so multi-season input isn't
    silently averaged together). Single-season input is unaffected."""
    if "season" in per_game_df.columns and per_game_df["season"].nunique() > 1:
        return ["season", key]
    return [key]


def performance_by_position(player_df: pd.DataFrame) -> pd.DataFrame:
    """Average points/rebounds/assists grouped by position (needs a `position` column)."""
    per_game_df = player_per_game_stats(player_df)
    group_cols = _season_aware_group(per_game_df, "position")
    return (
        per_game_df.groupby(group_cols)[["avg_points", "avg_rebounds", "avg_assists"]]
        .mean()
        .reset_index()
        .sort_values(group_cols[:-1] + ["avg_points"], ascending=[True] * (len(group_cols) - 1) + [False])
    )


def performance_by_tenure(player_df: pd.DataFrame) -> pd.DataFrame:
    """Average points/rebounds/assists grouped by years_on_team (needs a `years_on_team` column)."""
    per_game_df = player_per_game_stats(player_df)
    group_cols = _season_aware_group(per_game_df, "years_on_team")
    return (
        per_game_df.groupby(group_cols)[["avg_points", "avg_rebounds", "avg_assists"]]
        .mean()
        .reset_index()
        .sort_values(group_cols)
    )
