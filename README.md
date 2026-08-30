# Basketball Analytics — Phase 1

Ingests Israeli Basketball Super League season stats (`data/Basketball_Analytics.xlsx`)
into PostgreSQL and computes traditional + advanced metrics (TS%, eFG%,
AST/TOV, Per-36, efficiency index). `data/VIEWS.xlsx` and
`notebooks/Basketball Analytics.ipynb` are the original EDA/reference —
`test_analytics.py`'s output should match them for Maccabi Tel Aviv.

### Data coverage

`data/Basketball_Analytics.xlsx` originally shipped with real, full data for
**Maccabi Tel Aviv only** (14 players) plus season totals for all 13 teams.
The other 12 teams' players were added afterwards, sourced from the official
league site, **basket.co.il** (2023-24 season, regular season only), and
merged into the same 5 sheets — see the `Player_Data_Sources` sheet for the
exact source URL and caveats per team. `data/Basketball_Analytics.MTA_only_backup.xlsx`
is the pre-merge original, kept as a fallback.

`Roster.YearsOnTeam` is populated for every player (221 of 222 real players —
one player's site record is ambiguous, documented in `Player_Data_Sources`)
from basket.co.il's own "Years in Current Team" bio field, not
derived/estimated.

**Mid-season trades:** the `Roster`/`Player_Stats` model assumes one player =
one team per season, which a trade doesn't fit. The **`Transfers`** sheet
(loaded into `player_transfers` by `ingest.py`) is the connection table that
covers what that model can't: 6 players who changed teams in 2023-24, both
teams and each stint's real GP. For 5 of them (Kyle Feit, Alex Hamilton, Mike
McGuirl, Juvonte Reddic, Itay Moskovits) both stints are kept as two
independent rows in `Players_Details`/`Roster`/`Player_Stats` (one `PlayerId`
per team, the site's own per-stint ID), so `Player_Stats` totals for the
teams involved reconcile with basket.co.il's own team totals instead of
over/under-counting. The 6th (Isaiah Miles) is kept as a single combined row
at Hapoel Tel Aviv — see `Transfers.Note` per player for which case applies.
This means **225 rows for 222 real players** (not 222 rows / not 226). Each
stint row's per-game/PIR/shooting numbers are computed from *that stint only*
— nothing is duplicated or combined, so summing the rows gives the true
league totals. The dashboard marks these rows with a `*` next to the name
(team roster, all-players table, player card) plus a one-line note under the
table; each stint is independently selectable and appears under both clubs'
rosters. Home-page leader lists de-duplicate by name so a traded player is
ranked once, by his better stint.

**Known, corrected data-quality issue:** `Player_Stats.FGM`/`FGA` for all 14
Maccabi Tel Aviv players (and, from the same bug, Isaiah Miles' one combined
row) originally held **2-point field goals only**, not total field goals —
`3PM`/`3PA` was a separate, correctly-tracked category, so combined-shooting
metrics (eFG%, TS%) computed off the raw `FGM`/`FGA` were wrong for those 15
rows (silently for 9 of them, and detectably — `3PM/3PA > FGM/FGA`, impossible
in a real box score — for the other 6, which is what the dashboard's
data-quality flag originally caught). Fixed by re-deriving `FGM`/`FGA` as
2PT-made/attempted + 3PT-made/attempted, verified against each player's own
basket.co.il profile page and against `Team_Stats`' MTA row (see
`data/shooting_stat_investigation.md` for the full investigation, including
why summing `Player_Stats` didn't match `Team_Stats` for several other teams
— a separate season-length scope difference between the two sheets). The
dashboard's data-quality flag catches 0 player-seasons now.

**`Team_Stats` season-length fix:** that scope difference turned out to be
real and fixable, not just a documented caveat. The Winner League's regular
season has two stages — a 24-game round-robin, then a group stage where the
top 6 play 5 more rounds and the bottom 7 play 6-7 more (29-30 games total,
per the [2023-24 season format](https://en.wikipedia.org/wiki/2023%E2%80%9324_Israeli_Basketball_Premier_League))
— and `Team_Stats` originally only covered the first stage (22-24 GP) while
`Player_Stats` already covered both (29-30 GP, matching basket.co.il's own
"Regular Season" totals). `Team_Stats` has been re-pulled from basket.co.il
to cover the same full 29-30 game window, so both sheets are now on the same
scope (team-level totals still run ~9-12% above summing `Player_Stats`,
which is expected — team rebounds off dead balls are a real box-score
category no per-player row can capture). `MIN` in the refreshed `Team_Stats`
is an estimate (`GP × 40`) since basket.co.il's team-level table has no
minutes column at all.

**Playoffs:** 8 of the 13 teams qualified (MTA, HTA, IRG, HJM, HHL, EKA,
HHF, INZ — see the same Wikipedia page for the full bracket). Playoff stats
are modeled as a second stage of the *same* Winner League competition (not a
separate tournament) via a `competition` column (`regular_season` |
`playoffs`) on `team_season_stats`/`player_season_stats`, populated from
optional `Team_Stats_Playoffs`/`Player_Stats_Playoffs` sheets when present.
`test_analytics.py` defaults to `regular_season`; set
`COMPETITION=playoffs` to see the other. The Israel State Cup is a real,
separate cup competition these teams also played in 2023-24 — not modeled
yet, left for later.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in your DB credentials
```

`.env` needs a running PostgreSQL instance. Either a throwaway container:

```bash
docker run --name bball-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres
```

or the bundled compose stack (`docker compose up -d db`, then
`docker compose run --rm app <migrate|ingest|test|export>`).

### Credentials: `.env` vs AWS Secrets Manager

`db_client.py` reads the `DB_*` vars from `.env` by default. When
`DB_SECRET_ARN` (or `DB_SECRET_NAME`) is set it instead pulls
`{host,port,dbname,username,password}` from AWS Secrets Manager and ignores the
`DB_*` vars — that's the cloud path. `DB_SSLMODE` (default `prefer`) controls
TLS: `disable` for local Postgres, `require` for RDS.

### Deployment

See [`DEPLOY.md`](DEPLOY.md) and [`infra/`](infra/) (Terraform). Target: RDS
Postgres + the batch image on ECR + `dashboard.html`/`data.json` on S3 behind
CloudFront.

## Run

```bash
python ingest.py               # creates the schema (if needed) and loads data/Basketball_Analytics.xlsx
python test_analytics.py       # queries the DB, computes metrics, prints leaderboards
python export_dashboard_data.py  # regenerates ./data.json for the dashboard
```

Re-running `ingest.py` is safe — it upserts, so it won't duplicate rows. When
`schema.sql` changes shape (there's no migration tool — the cloud DB starts
empty), `python scripts/reset_db.py --yes` drops the tables so the next
`ingest.py` recreates them. `ingest.py --workbook <path>` (or `$WORKBOOK`) plus
`$SEASON` ingests a different season's file.

## Dashboard

`dashboard.html` is a static dashboard over the same season stats. It
`fetch()`es `./data.json` at load (generated by `export_dashboard_data.py` from
the DB — the old hand-pasted `const DATA` blob is gone), so it must be **served
over HTTP**, not opened as a `file://` — `python -m http.server 8000` from the
project root, then <http://localhost:8000/dashboard.html>. A few dashboard-only
fields the DB doesn't hold (team standings `rank`, source row order, the age
reference date) come from `dashboard_supplement.json`. It has a
language toggle (top right) with **Hebrew as the default** and English as the
alternative; team and player names switch with it (sourced from basket.co.il,
see `data/hebrew_names.json`), while stat abbreviations (PTS, AST, REB, FG%,
PIR, GP, position codes, …) stay in English in both languages, matching normal
Israeli basketball-media convention. It also has a **regular season / playoffs**
toggle (top right, next to the language switch) — same `competition` split as
the database (see below). Both choices are remembered per-browser
(`localStorage`). `data.json` is season-keyed
(`{default_season, seasons:{…}}`) so more seasons can be added without touching
the loader; the in-page season selector is not built yet.

It's also responsive down to phone widths (~360px+): the topbar reflows to
3 rows, hero type scales with `clamp()`, and the League/Roster tables fall
back to horizontal scroll (`.table-wrap{overflow-x:auto}`) below 640px — a
sticky pinned name column was tried but hit a reproducible Chromium
`position:sticky` + CSS-grid-item offset bug under real scroll, so it was
dropped rather than shipped broken; plain scrolling works correctly. The
mobile breakpoint is driven by both a CSS `@media` query and a JS-measured
`window.innerWidth` fallback (`html[data-mobile]`) — needed because a
`<meta viewport>` tag has no effect inside an `<iframe>`, which is how this
page is actually shown when opened as a published Artifact link rather than
a local file.

The League and Roster tables have **click-to-sort column headers** (first
click sorts a numeric column descending / a text column ascending, second
click reverses it, with a ▲/▼ indicator on the active column) and a
**search box** that filters rows by the currently-displayed team/player name
(so it matches whichever language is active). Both are per-table UI state,
not wired into the URL or `localStorage` — `goTab` / `goTeam` /
`setCompetition` call `resetRosterUI()` / `resetLeagueUI()` /
`resetPlayersUI()` so a stale query can't silently filter the next team's
roster (or a competition's dataset) down to "no results". The Player-tab
list filters survive the list→card→back round trip (the back link doesn't
reset) but not a nav-tab click.
Each keystroke re-runs the whole `render()`, which rebuilds the `<input>`, so
`render()` stashes the caret position (module-level `searchFocus`, set only
by the keystroke's own handler) and restores focus to the fresh
`.search-input` afterwards — otherwise typing drops focus every character.

Both tables' toolbars also carry an **Export CSV** button (`btn_export` —
"ייצוא נתונים" / "Export CSV"). It writes exactly what's on screen: the
filtered + sorted rows, with the Roster export following the active Totals /
Per Game / Per 36 mode (column headers gain the `/36` suffix accordingly).
`downloadCSV()` prepends a UTF-8 BOM (`U+FEFF`) so Hebrew opens cleanly in
Excel, and triggers `league_stats.csv` / `team_roster_stats.csv` via a
transient object-URL `<a download>`. (That works when `dashboard.html` is a
local file; a sandboxed artifact iframe blocks script-triggered downloads.)

A 5th tab, **Advanced Analytics** (Hebrew: ניתוחים מתקדמים), adds
cross-player/cross-team tools, both hand-rolled inline SVG/HTML (no charting
library), colors validated against this project's own `dataviz` skill
(`validate_palette.js`, `--pairs all`, against this page's real dark panel
surface `#11161D`). A **Players / Teams** toggle at the top of the page picks
which of the two is shown (Players first by default), so only one analysis
surface is on screen at a time:
- **Player comparison** — pick up to 4 players; grouped horizontal bars per
  metric (Points, Rebounds, Assists, PIR, TS%), one color per player,
  defaulting to the top 2 by PIR.
- **Team comparison radar** — pick 2 teams; a 6-axis radar (Points, Assists,
  Rebounds, Blocks, Turnovers, PIR), min-max normalized against the full
  active team set — inspired by the same chart in the project's original
  `notebooks/Basketball Analytics.ipynb`, with one deliberate fix: the
  Turnovers axis is inverted (lower turnovers = bigger spike) so "bigger is
  better" holds on every axis, unlike the notebook's raw normalization.

A points-vs-efficiency scatter was tried first, then dropped at the user's
request in favor of the two tools above.

The Roster table also gained a **Per Mode** toggle (Totals / Per Game /
Per 36, matching NBA.com/Stats' convention) and both the League and Roster
tables now **tint each stat cell by its percentile** within the full active
pool (team or roster — always the *whole* pool, not the search-filtered
view, so a tint reflects true standing even mid-search) — a single-hue
(app accent) background wash, inverted for Turnovers so a low value still
reads as "good." This replaced the old binary top-15%-highlight that only
existed on the PIR column. The player page's **Advanced metrics** panel
(Per-36 Pts/Ast/Reb, EFF, AST/TOV) — already computed by `metrics.py` and
embedded in `DATA`, just never rendered before this — remains unchanged.

### Player tab: list view → card view

The **Player** tab has two views (`state.playerView`), dispatched by
`renderPlayer()`:

- **`list`** (default, `renderPlayerList`): the whole league in one
  sortable/filterable table — Player, Team, Pos, Age, GP, MIN, PTS, REB, AST,
  PIR, FG%, 3P%, TS%. Click-to-sort headers (`PLAYERS_COLUMNS` +
  `buildSortableHead`/`sortRows`), default **PTS descending**. Three filters
  above it: a name search (keeps focus across keystrokes like the other
  tables), a **position** dropdown (the five slots — a hybrid player matches
  either of his), and a **team** dropdown. A **Totals / Per Game / Per 36**
  toggle (shared `state.statMode`) drives the counting columns; the shooting
  rates don't move.
- **`detail`** (`renderPlayerCard`): the full single-player card (hero, quad,
  shooting/usage/bio, the **Player Analytics & Visualization suite** below,
  Stats-by-season, rule-based insights, half-court shot map, vs-position).
  Reached by clicking any player row anywhere in the app (`goPlayer` sets
  `playerView='detail'`); a "← All players" link up top returns to the list,
  and navigating to the tab from the nav always resets to `list`.

#### Player Analytics & Visualization suite

Sits between the hero card and the Stats-by-season table on the player
`detail` view. Every number is derived from season-total box-score fields
already in `data.json` — no shot (x, y) coordinates, no play-by-play, no game
logs, no per-player steals/blocks/fouls/usage — so the design leans on
percentile-vs-peer framing rather than pretending to spatial data. All charts
are hand-rolled inline SVG/HTML, colours from the `dataviz` skill palette.

- **8-axis player skill radar** (`playerSkillRadarPanel` → `buildSkillRadar`,
  `playerSkillAxes`) — Scoring, Shooting eff., Playmaking, Ball security,
  Rebounding, Perimeter, Inside finish, Impact. Each axis is a **0–100
  percentile rank** (`percentileOf`) inside the player's comparison pool:
  same-position qualified players, falling back to the whole league when that
  sample is thin (`courtPool('position', …)`). Every input is minutes-neutral
  (per-36 or a rate) and Ball security is the turnover rate **inverted**, so a
  bigger spike on any axis always means "better vs peers". Axes with too few
  attempts to be meaningful (Perimeter needs ≥ 15 3PA, Inside ≥ 15 2PA) score 0.
- **Head-to-head 2-player comparison** — a "Compare vs" `<select>` in the radar
  panel (`state.playerCmpId`, reset in `normalizeSelection` on any dataset
  switch). Picking a second player overlays their polygon in the second series
  colour and adds a side-by-side table (`playerRadarCompareTable`): PTS / REB /
  AST per-36, TS%, eFG%, AST:TOV, PIR/36. The comparison player's legend name
  is a link to their own card.
- **Player-level Four Factors** (`playerFourFactorsPanel`) — eFG%, turnover
  rate, offensive rebounds per-36, and free-throw rate, each a diverging bar
  measured against the **position-pool median** (green = better side, amber =
  worse), reusing the `.ff-*` styling from the team Four Factors view. Shown
  only when the player has ≥ 20 FGA.
- **Player signature / archetype** (`playerSignatureCard`, `playerArchetype`) —
  a plain-language archetype label chosen from the two highest skill axes
  (Floor spacer · shot maker / Floor general / Interior anchor / Glass-crashing
  guard / Go-to scorer / Two-way connector), the **top-3 strengths** and
  **bottom-2 weaknesses** by percentile, and a **career-trend arrow** comparing
  this season's PIR/36 to last season's, read across every season on record via
  `playerCareerRows(pid)` scanning `RAW.seasons`.

#### Half-court shot map & shot-volume rail

`buildHalfCourt` / `courtLegend` / `courtZoneTable` / `shotVolumeBar`, shared by
the player card (`playerShotCourtPanel`) and the Advanced-Analytics **Shot
Profile** sub-tab (`renderShotCourt`). Three real zones are all the box-score
splits support — Paint · 2PT `(FGM−3PM)/(FGA−3PA)`, Perimeter · 3PT, and the
Free-throw line — filled by a diverging heat colour of the zone's FG% vs the
comparison-pool median (`shotZones`, `zoneMedians`, `heatColor`).

The rework prioritises legibility: makes/attempts, volume and vs-median move
**off the court** into a right-rail table, leaving only a short zone tag and a
large FG% on the floor itself; always-visible white zone dividers keep the
three regions distinct even when their colours are close; the old 3-swatch key
becomes a labelled **diverging efficiency scale** (−8 … 0 … +8 pp, plus a
separate "no attempts" chip). A new **100 % stacked shot-volume distribution**
bar in the rail shows each zone's share of attempts with the raw attempt count
— explicitly labelled as a zone split, since there is no shot-level location
data to plot a true shot chart.

The player card also has a **Stats by season** panel (below the headline
card), modeled on NBA.com/Stats' player pages: the hero card up top is the
player's general season line, and this panel below it has its own
**Calculation** toggle (Totals / Per Game / Per 36) and **Split** toggle
(Regular season / Playoffs), then renders one row per season — Season, Team,
Age, GP, MIN, PTS, REB, AST, PIR, FG%, 3P%, FT%, eFG%, TS%. Only 2023-24
exists today; the `seasonRows` array in `renderPlayer` is the single place
to extend once more seasons are ingested. Both toggles are independent of the
top-bar regular-season/playoffs switch (which still drives the rest of the
page), and a player with no rows in the chosen split shows an empty note
instead of the table.

**Mid-season moves** are surfaced in context rather than in one collected
place: `isMultiStint(p)` (name appears on >1 row in `DATA.players`) puts a
`*` next to the player's name in the team roster, the all-players table, and
the player card, with a one-line `stint_note` under each of those tables
explaining that the row covers only that club's stint. The old Home-page
transfers panel / `<details>` is gone.

Other player-page details: the hero shows the position as its own bordered
**pill** under the name (was buried in the small eyebrow line, which now
carries only team · jersey), the roster picker `<select>` lists names without
the position suffix, and the lower panel is split into two columns by kind —
the left column holds everything season-dependent (**קליעה / Shooting** bars
plus a ruled-off **נתוני משחק / Playing load**: games, minutes), the right
column holds only the fixed **פרטים אישיים / Bio** (age, height, nationality,
tenure). Nationality is resolved through a `COUNTRY` map (`nationalityDisplay`)
that normalizes the source's free-text values ("United States (USA)", "USA",
"USA/Israel", bare "ISR", …) to a Hebrew/English name that follows the
language toggle. Windows has no flag-emoji font (regional-indicator pairs
render as bare letters "IL"/"US"), so flags ship as tiny hand-built inline
**SVGs** (`FLAGS` map, `_hb`/`_vb` band helpers) — stylised where a flag
carries an emblem, at a size where the simplification doesn't read.

Positions: there are **five slots** (`POS_SLOTS` = PG/SG/SF/PF/C). The source
also carries hybrid codes (`G`, `F`, `G-F`, `F-C`); `posGroups()` /
`POS_MAP` collapse each to one or two slots, **primary first** — `G` →
PG/SG, `F` → SF/PF, `G-F` → SG/SF, `F-C` → PF/C. `posLabel()` joins them with
a slash for display ("SG/SF"), the position **filter** on the Player tab
offers only the five slots, and a hybrid player matches whichever of his
slots is selected. `positionFull()` spells the slot(s) out in English
("Shooting guard / Small forward") and keeps the code in Hebrew — the same
English-abbreviation convention the stat headers follow in both languages.

### Home page (was "Overview")

The first tab is **עמוד הבית / Home**. It keeps the season hero (team/player
counts), but its body is now **league leaders in every category**,
`renderOverview` → `leaderCard()`:

- **Leaders by player** (top): Points, Rebounds, Assists, PIR, Minutes, TS%,
  eFG%, FG%, 3P%, FT%, AST/TOV — one card each, #1 shown large with ranks
  2-5 listed under it. Restricted to players with `gp ≥ minGP`, where
  `minGP = max(3, round(0.4 × max GP))` so the bar scales down for the
  short playoff sample. Trade players (two rows) are de-duplicated by name.
- **Leaders by team** (below): Points, Assists, Rebounds, Off/Def rebounds,
  Blocks, Fewest turnovers (ascending), PIR, 3PM, 3P%.

The data-quality card now renders only when `activeBadSplitCount() > 0`
(it's 0 for 2023-24), and the old "team offense, ranked" bar list, the
top-4-by-PIR list, and the mid-season-moves panel were all removed — the
first two replaced by the leader grids, moves now shown in context (see
"Mid-season trades" above).

## Project layout

| File | Purpose |
|---|---|
| `schema.sql` | Table definitions: `teams`, `players`, `player_id_map`, `roster` (season-keyed), `team_season_stats`, `player_season_stats`, `player_transfers` |
| `db_client.py` | SQLAlchemy engine/session from `.env` or AWS Secrets Manager, TLS opts, `init_db()` |
| `ingest.py` | Loads a season workbook (`--workbook`/`$WORKBOOK`) into Postgres |
| `metrics.py` | Shooting %, TS%, eFG%, AST/TOV, Per-36, efficiency index, grouped views |
| `test_analytics.py` | Queries + prints leaderboards for manual verification against `data/VIEWS.xlsx` |
| `export_dashboard_data.py` | Regenerates `data.json` from the DB (`--check` diffs vs a reference) |
| `dashboard.html` + `data.json` | Static bilingual dashboard; loads `data.json` at runtime — see [Dashboard](#dashboard) |
| `dashboard_supplement.json` | Dashboard fields not in the DB: team `rank`, row order, `age_as_of` |
| `scripts/reset_db.py` | Drop all tables so `schema.sql` re-applies (no migration tool) |
| `scripts/qa_audit_agent.js` | One-command quality gate — math invariants + metadata + team-metrics integrity + Playwright visual/RTL sweep (8 viewports); Markdown report, exit 0 iff all green. `--skip-visual`, `--json` |
| `scripts/scrape_player_details.py` | Backfill missing jersey numbers into `data.json` from `team.asp` roster widgets (cache-shared with `scrape_league.py`); also normalises `name_he` nickname quoting (`"…"` → `״…״`) and the `jersey: 0` sentinel. Does not fabricate — the league source lacks a number for ~25 % of stat-only appearances |
| `Dockerfile` · `docker-compose.yml` · `docker-entrypoint.sh` | Batch image (`migrate`/`ingest`/`export`/`test`) + local stack |
| `infra/` · `DEPLOY.md` · `.github/workflows/` | Terraform for AWS, deploy runbook, CI |
| `data/hebrew_names.json` | Team/player Hebrew names sourced from basket.co.il, merged in by `export_dashboard_data.py` |
| `data/shooting_stat_investigation.md` | Investigation + fix for the MTA/Isaiah Miles FGM-FGA bug and the `Player_Stats` vs `Team_Stats` scope mismatch — see "Known, corrected data-quality issue" above |
| `data/playoffs_data.json` | Raw playoff team/player totals sourced from basket.co.il, merged into `Team_Stats_Playoffs`/`Player_Stats_Playoffs` |
