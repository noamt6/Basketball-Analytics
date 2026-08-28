"""
Loads data/Basketball_Analytics.xlsx into PostgreSQL.

The workbook has 5 core sheets: Teams_Details, Team_Stats, Players_Details,
Roster, Player_Stats. Team_Stats / Player_Stats are SEASON TOTALS (they
carry a GP column), not per-game box scores — they map onto
team_season_stats / player_season_stats, tagged with the SEASON env var
since the source file itself has no season column, and with a `competition`
column ('regular_season' | 'playoffs') distinguishing the two stages of the
Winner League season. Optional Team_Stats_Playoffs / Player_Stats_Playoffs
sheets (only 8 of 13 teams qualified) are merged in the same way if present.

Loading is idempotent: every insert is an upsert
(INSERT ... ON CONFLICT DO UPDATE), so re-running ingest.py is safe.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from db_client import get_engine, init_db

DATA_PATH = Path(__file__).parent / "data" / "Basketball_Analytics.xlsx"
SEASON = os.getenv("SEASON", "2023-2024")


def resolve_data_path() -> Path:
    """Workbook path, in priority order: --workbook arg, $WORKBOOK, the bundled
    data/Basketball_Analytics.xlsx. Lets a second season be ingested with just
    `SEASON=2024-2025 WORKBOOK=/path/to/next.xlsx python ingest.py`."""
    parser = argparse.ArgumentParser(description="Load a season workbook into PostgreSQL.")
    parser.add_argument("--workbook", type=Path, default=None,
                        help="Path to the season .xlsx (default: $WORKBOOK or the bundled workbook)")
    args, _ = parser.parse_known_args()
    if args.workbook:
        return args.workbook
    env = os.getenv("WORKBOOK")
    return Path(env) if env else DATA_PATH

# Common season-stats column mapping shared by Team_Stats and Player_Stats.
STATS_COLUMN_MAP = {
    "GP": "gp", "MIN": "min", "PTS": "pts", "FGM": "fgm", "FGA": "fga",
    "FG%": "fg_pct", "3PM": "fg3m", "3PA": "fg3a", "3P%": "fg3_pct",
    "FTM": "ftm", "FTA": "fta", "FT%": "ft_pct", "OREB": "oreb",
    "DREB": "dreb", "REB": "reb", "AST": "ast", "TOV": "tov",
    "STL": "stl", "BLK": "blk", "PIR": "pir",
}


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of row dicts with every NaN/NaT/NA turned into None,
    so nullable INTEGER/DATE columns get SQL NULL instead of a float 'NaN'
    (which Postgres rejects as 'integer out of range')."""
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


def _upsert(conn: Connection, table: Table, records: list[dict], pk_cols: list[str]) -> None:
    if not records:
        return
    stmt = pg_insert(table).values(records)
    update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk_cols}
    stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
    conn.execute(stmt)


def load_teams(xls: pd.ExcelFile) -> pd.DataFrame:
    df = pd.read_excel(xls, "Teams_Details")
    return df.rename(columns={
        "TeamID": "team_id", "TeamName": "team_name", "City": "city",
        "MainSponsor": "main_sponsor", "Arena": "arena",
    })


PLAYER_COLS = ["player_id", "first_name", "last_name", "nationality", "birth_date", "height_m"]
ROSTER_COLS = ["player_id", "season", "team_id", "position", "jersey_number", "years_on_team"]


def load_players(xls: pd.ExcelFile) -> pd.DataFrame:
    """`players` is a pure identity table now — no team_id (that's season-
    specific and lives in `roster`)."""
    df = pd.read_excel(xls, "Players_Details")
    df = df.rename(columns={
        "PlayerId": "player_id", "FirstName": "first_name", "LastName": "last_name",
        "Nationality": "nationality", "BirthDate": "birth_date", "Height": "height_m",
    })
    df["birth_date"] = pd.to_datetime(df["birth_date"]).dt.date
    return df[PLAYER_COLS]


def load_roster(xls: pd.ExcelFile) -> pd.DataFrame:
    df = pd.read_excel(xls, "Roster")
    df = df.rename(columns={
        "PlayerId": "player_id", "Position": "position",
        "JerseyNumber": "jersey_number", "YearsOnTeam": "years_on_team",
        "TeamID": "team_id",
    })
    df["season"] = SEASON
    return df[ROSTER_COLS]


def build_player_id_map(players: pd.DataFrame) -> pd.DataFrame:
    """
    Maps this workbook's source PlayerId onto the canonical players.player_id.

    For 2023-2024 the source IDs ARE canonical, so this is the identity map; it
    exists so a later season whose workbook renumbers or reuses IDs (traded
    players, Maccabi Tel Aviv's private 100-113 range) can be resolved onto the
    right person here — match on name + birth_date, or a hand-built mapping
    sheet — before its roster/stats rows are upserted.
    """
    ids = players["player_id"].dropna().astype(int).unique()
    return pd.DataFrame({"season": SEASON, "source_player_id": ids, "player_id": ids})


def load_team_season_stats(xls: pd.ExcelFile) -> pd.DataFrame:
    """
    Team_Stats holds the Winner League regular season (round-robin + upper/
    lower house groups, ~29-30 GP for every team). Team_Stats_Playoffs is an
    optional sheet — only 8 of the 13 teams qualified for the playoffs
    (quarterfinal/semifinal/final) — same stage of the same competition, not
    a separate tournament, tagged via `competition` rather than a second
    table.
    """
    df = pd.read_excel(xls, "Team_Stats")
    df = df.rename(columns={"TeamId": "team_id", **STATS_COLUMN_MAP})
    df["season"] = SEASON
    df["competition"] = "regular_season"

    if "Team_Stats_Playoffs" in xls.sheet_names:
        po = pd.read_excel(xls, "Team_Stats_Playoffs")
        po = po.rename(columns={"TeamId": "team_id", **STATS_COLUMN_MAP})
        po["season"] = SEASON
        po["competition"] = "playoffs"
        df = pd.concat([df, po], ignore_index=True)

    return df


def load_player_season_stats(xls: pd.ExcelFile) -> pd.DataFrame:
    """See load_team_season_stats — Player_Stats_Playoffs is the equivalent
    optional sheet at player granularity (only players who actually
    appeared in a playoff game have a row)."""
    df = pd.read_excel(xls, "Player_Stats")
    df = df.rename(columns={"PlayerId": "player_id", **STATS_COLUMN_MAP})
    df["season"] = SEASON
    df["competition"] = "regular_season"
    _warn_inconsistent_shooting_splits(df)

    if "Player_Stats_Playoffs" in xls.sheet_names:
        po = pd.read_excel(xls, "Player_Stats_Playoffs")
        po = po.rename(columns={"PlayerId": "player_id", **STATS_COLUMN_MAP})
        po["season"] = SEASON
        po["competition"] = "playoffs"
        _warn_inconsistent_shooting_splits(po)
        df = pd.concat([df, po], ignore_index=True)

    return df


def load_transfers(xls: pd.ExcelFile) -> pd.DataFrame:
    """
    Players who played for two teams in the same season. Optional sheet —
    only present once someone has actually gone looking for mid-season
    trades (see README "Data coverage"); returns an empty frame if absent.
    """
    if "Transfers" not in xls.sheet_names:
        return pd.DataFrame(columns=[
            "player_name", "season", "team_id_a", "gp_a", "team_id_b", "gp_b", "note",
        ])
    df = pd.read_excel(xls, "Transfers")
    df = df.rename(columns={
        "PlayerName": "player_name", "Season": "season", "TeamA": "team_id_a",
        "GP_A": "gp_a", "TeamB": "team_id_b", "GP_B": "gp_b", "Note": "note",
    })
    df["player_id"] = df["KeptPlayerId"].astype("Int64")  # nullable int; NaN -> pandas.NA -> None
    df["player_id"] = df["player_id"].astype(object).where(df["player_id"].notna(), None)
    return df[["player_id", "player_name", "season", "team_id_a", "gp_a", "team_id_b", "gp_b", "note"]]


def _warn_inconsistent_shooting_splits(df: pd.DataFrame) -> None:
    """
    Flag rows where 3PA/3PM exceed total FGA/FGM — a data-quality issue found
    in the source spreadsheet (3-pointers should be a subset of field goals).
    Any metric combining fgm/fga with fg3m/fg3a (eFG%, TS%) will be
    nonsensical for these rows until the source data is corrected.
    """
    bad = df[(df["fg3a"] > df["fga"]) | (df["fg3m"] > df["fgm"])]
    if not bad.empty:
        ids = ", ".join(str(i) for i in bad["player_id"])
        print(
            f"WARNING: {len(bad)} player_season_stats row(s) have 3PA/3PM > FGA/FGM "
            f"(player_id: {ids}). eFG%/TS% will be unreliable for these players until "
            "the source FG/3P columns are corrected."
        )


def run(data_path: Path = DATA_PATH) -> None:
    init_db()
    engine = get_engine()
    metadata = MetaData()
    metadata.reflect(bind=engine, only=[
        "teams", "players", "player_id_map", "roster",
        "team_season_stats", "player_season_stats", "player_transfers",
    ])

    xls = pd.ExcelFile(data_path)
    teams = load_teams(xls)
    players = load_players(xls)
    id_map = build_player_id_map(players)
    roster = load_roster(xls)
    team_stats = load_team_season_stats(xls)
    player_stats = load_player_season_stats(xls)
    transfers = load_transfers(xls)

    with engine.begin() as conn:
        _upsert(conn, metadata.tables["teams"], _records(teams), ["team_id"])
        _upsert(conn, metadata.tables["players"], _records(players), ["player_id"])
        _upsert(conn, metadata.tables["player_id_map"], _records(id_map),
                ["season", "source_player_id"])
        _upsert(conn, metadata.tables["roster"], _records(roster), ["player_id", "season"])
        _upsert(conn, metadata.tables["team_season_stats"], _records(team_stats),
                ["team_id", "season", "competition"])
        _upsert(conn, metadata.tables["player_season_stats"], _records(player_stats),
                ["player_id", "season", "competition"])
        _upsert(conn, metadata.tables["player_transfers"], _records(transfers),
                ["player_name", "season", "team_id_a", "team_id_b"])

    print(
        f"Ingested {len(teams)} teams, {len(players)} players, {len(roster)} roster rows, "
        f"{len(team_stats)} team_season_stats rows, {len(player_stats)} player_season_stats rows, "
        f"{len(transfers)} player_transfers rows (season={SEASON})."
    )


if __name__ == "__main__":
    run(resolve_data_path())
