# Multi-season scraping — `scrape_league.py`

Standalone scraper for **basket.co.il** (Israeli Basketball Premier / "Winner"
League), the same source `data/Basketball_Analytics.xlsx` was hand-built from.
It produces one **ingest-ready workbook per season**; it does not talk to the DB
unless you pass `--ingest`, and it never touches `dashboard.html` / frontend.

## Install

```bash
pip install -r requirements.txt   # now also pulls requests + beautifulsoup4 + lxml
```

## Use

```bash
# last 10 seasons, ending 2025-2026 -> data/scraped/Basketball_Analytics_<season>.xlsx
python scrape_league.py

# explicit range / list
python scrape_league.py --seasons 2016-2017..2025-2026
python scrape_league.py --seasons 2021-2022,2024-2025

# smoke test: one season, few players, fast, no per-player bio pages
python scrape_league.py --seasons 2022-2023 --limit 20 --skip-bios --delay 0.3

# scrape AND load straight into Postgres (needs a live DB / .env)
python scrape_league.py --seasons 2016-2017..2025-2026 --ingest
```

Then, if you didn't use `--ingest`:

```bash
for f in data/scraped/*.xlsx; do
  s=$(basename "$f" .xlsx | sed 's/Basketball_Analytics_//')
  SEASON=$s WORKBOOK=$f python ingest.py
done
```

`ingest.py` is idempotent (upserts), so re-runs are safe. After loading, sanity
check with `python scripts/check_data_quality.py --fail-on fg` and
`python test_analytics.py`.

Fetched HTML is cached under `.scrape_cache/` (git-ignored) — delete it to
force a refetch. `--debug-dump <dir>` also keeps a copy of every page.
`data/scraped/` is git-ignored.

## Source pages

| what | URL | notes |
|---|---|---|
| team list + rank | `table.asp?cYear=<Y>` | `cYear` = year the season **ends** (2024 → 2023-2024) |
| player season **totals** | `stats-accumulate.asp?cYear=<Y>&c=<page>` | true totals with makes/attempts; paginated by `&c=` |
| roster + bios | `team.asp?TeamId=<id>&cYear=<Y>` | jersey, position, height, birth date |
| nationality | `player.asp?PlayerId=<id>` | flag-image alt text only; skipped with `--skip-bios` |

## How it maps to the schema

`PlayerId` from the site is stable across seasons, so it is used directly as the
canonical `players.player_id`. The per-season team id from `table.asp` becomes
`teams.team_id` (a season registration id — the same club can carry different
ids in different seasons, as `schema.sql` already notes for players).

Two-pointers + threes from the site are summed into `fgm/fga`; `pir` = the
site's `VAL`; `dreb/oreb/reb` = `DR/OR/TR`; `blk` = `BKF`.

## Known gaps (deliberate; fill in later)

- **Playoffs** are not scraped — only `competition = 'regular_season'`. The
  site keeps playoff totals behind a different board param.
- **`Team_Stats` is aggregated from the scraped player rows** (sum per team,
  percentages recomputed). The site's team page is per-game and gives
  percentages only, no makes. Team rebounds / bench noise mean this won't tie
  out exactly to the site — `scripts/check_data_quality.py` check 2 is the
  yardstick, same as for the shipped workbook.
- `Teams_Details` city / sponsor / arena and `Roster.years_on_team` aren't on
  the scraped pages → `NULL` (all nullable in `schema.sql`).
- Mid-season transfers aren't reconstructed; `Roster` keeps the first team seen
  for a player in a season.

All parsing lives in pure `parse_*(html) -> rows` functions, so a markup change
is a one-function fix. Verified against `cYear=2023` (2022-2023).
