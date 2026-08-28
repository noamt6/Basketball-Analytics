-- Basketball Analytics — Phase 1 schema
-- Mirrors the real source data in data/Basketball_Analytics.xlsx:
--   Teams_Details, Team_Stats, Players_Details, Roster, Player_Stats
-- Team_Stats / Player_Stats hold SEASON TOTALS (a GP column), not per-game
-- box scores, so they are modeled as *_season_stats tables. A `season`
-- column is added (absent from the source file, which covers one season)
-- so the schema can hold multiple seasons later without a migration.
--
-- `competition` (added alongside `season`) separates the Winner League
-- regular season (round-robin + upper/lower house groups, ~29-30 GP) from
-- its playoffs (quarterfinal/semifinal/final, best-of-series) — two stages
-- of the SAME league competition, not two different tournaments. Values:
-- 'regular_season' (default) | 'playoffs'. Only 8 of the 13 teams (and
-- their players who actually appeared) have 'playoffs' rows; the rest
-- didn't qualify. Room is left for other real, separate competitions later
-- (e.g. the Israel State Cup) as additional `competition` values.
--
-- NOTE: `init_db()` only runs CREATE TABLE IF NOT EXISTS — it never ALTERs an
-- existing table. When this file changes shape (the `competition` column on the
-- stats tables; the `season` column + widened PK on `roster`; the removal of
-- `players.team_id`; the new `player_id_map` table), an existing local database
-- won't pick the change up automatically. Drop and recreate the affected tables
-- (or the whole DB) and re-ingest — ingest is idempotent and takes seconds.
--
-- MULTI-SEASON: the stats tables and `player_transfers` already key on `season`.
-- `roster` now does too (a player's team / position / jersey / tenure vary by
-- season). `players` and `teams` are pure identity tables — one row per real
-- person / franchise across all seasons. `player_id_map` resolves the source
-- workbook's unstable per-season IDs (traded players get one ID per team; the
-- Maccabi Tel Aviv rows use a private 100-113 numbering a later workbook can
-- collide with) onto the canonical `players.player_id` used everywhere else.

CREATE TABLE IF NOT EXISTS teams (
    team_id      VARCHAR(10)  PRIMARY KEY,
    team_name    VARCHAR(100) NOT NULL,
    city         VARCHAR(100),
    main_sponsor VARCHAR(100),
    arena        VARCHAR(100)
);

-- Identity table: one row per real person, stable across seasons. Season-
-- specific facts (which team, position, jersey, tenure) live in `roster`.
CREATE TABLE IF NOT EXISTS players (
    player_id  INTEGER      PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name  VARCHAR(100) NOT NULL,
    nationality VARCHAR(100),
    birth_date DATE,
    height_m   NUMERIC(3,2)
);

-- Maps the source workbook's per-season player IDs onto the canonical
-- players.player_id. For 2023-2024 the mapping is the identity (source ID ==
-- canonical ID); it exists so a later season whose workbook reuses/renumbers
-- IDs can point at the right person without overwriting anyone.
CREATE TABLE IF NOT EXISTS player_id_map (
    season           VARCHAR(20) NOT NULL,
    source_player_id INTEGER     NOT NULL,
    player_id        INTEGER     NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    PRIMARY KEY (season, source_player_id)
);

-- Team membership for one player in one season.
CREATE TABLE IF NOT EXISTS roster (
    player_id     INTEGER     NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    season        VARCHAR(20) NOT NULL,
    team_id       VARCHAR(10) NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    position      VARCHAR(10),
    jersey_number INTEGER,
    years_on_team INTEGER,
    PRIMARY KEY (player_id, season)
);

CREATE TABLE IF NOT EXISTS team_season_stats (
    team_id     VARCHAR(10)  NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    season      VARCHAR(20)  NOT NULL,
    competition VARCHAR(20)  NOT NULL DEFAULT 'regular_season',
    gp      INTEGER,
    min     INTEGER,
    pts     INTEGER,
    fgm     INTEGER,
    fga     INTEGER,
    fg_pct  NUMERIC(5,2),
    fg3m    INTEGER,
    fg3a    INTEGER,
    fg3_pct NUMERIC(5,2),
    ftm     INTEGER,
    fta     INTEGER,
    ft_pct  NUMERIC(5,2),
    oreb    INTEGER,
    dreb    INTEGER,
    reb     INTEGER,
    ast     INTEGER,
    tov     INTEGER,
    stl     INTEGER,
    blk     INTEGER,
    pir     INTEGER,
    PRIMARY KEY (team_id, season, competition)
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id   INTEGER      NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    season      VARCHAR(20)  NOT NULL,
    competition VARCHAR(20)  NOT NULL DEFAULT 'regular_season',
    gp        INTEGER,
    min       INTEGER,
    pts       INTEGER,
    fgm       INTEGER,
    fga       INTEGER,
    fg_pct    NUMERIC(5,2),
    fg3m      INTEGER,
    fg3a      INTEGER,
    fg3_pct   NUMERIC(5,2),
    ftm       INTEGER,
    fta       INTEGER,
    ft_pct    NUMERIC(5,2),
    oreb      INTEGER,
    dreb      INTEGER,
    reb       INTEGER,
    ast       INTEGER,
    tov       INTEGER,
    stl       INTEGER,
    blk       INTEGER,
    pir       INTEGER,
    PRIMARY KEY (player_id, season, competition)
);

-- Players who played for two teams in the same season (mid-season trades).
-- roster/player_season_stats model "one player, one team" per season, which
-- doesn't fit a trade — this is the connection table that captures the part
-- that model can't: which two teams, and how many games at each. player_id
-- is nullable because two source-site player IDs sometimes exist for the
-- same real person (one per team registration) with no single row to point
-- at; team_a/gp_a and team_b/gp_b stand on their own either way.
CREATE TABLE IF NOT EXISTS player_transfers (
    id         SERIAL PRIMARY KEY,
    player_id  INTEGER REFERENCES players(player_id) ON DELETE SET NULL,
    player_name VARCHAR(200) NOT NULL,
    season     VARCHAR(20)  NOT NULL,
    team_id_a  VARCHAR(10)  NOT NULL REFERENCES teams(team_id),
    gp_a       INTEGER,
    team_id_b  VARCHAR(10)  NOT NULL REFERENCES teams(team_id),
    gp_b       INTEGER,
    note       VARCHAR(255),
    UNIQUE (player_name, season, team_id_a, team_id_b)
);

CREATE INDEX IF NOT EXISTS idx_roster_team_id ON roster(team_id);
CREATE INDEX IF NOT EXISTS idx_roster_season ON roster(season);
CREATE INDEX IF NOT EXISTS idx_player_id_map_player_id ON player_id_map(player_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_season ON player_season_stats(season);
CREATE INDEX IF NOT EXISTS idx_team_season_stats_season ON team_season_stats(season);
CREATE INDEX IF NOT EXISTS idx_player_transfers_season ON player_transfers(season);
