"""
Drop every application table so `python -m db_client` (or `ingest.py`, which
calls init_db()) can recreate them from the current schema.sql.

We deliberately don't use migrations (the cloud DB starts empty and re-ingest
takes seconds), so this is how a schema.sql shape change is applied locally:

    python scripts/reset_db.py --yes
    python ingest.py

DESTRUCTIVE. Requires --yes. Never run against a database you can't rebuild
from the workbook.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from db_client import get_engine  # noqa: E402

# child tables first (CASCADE covers FKs anyway, but keep it readable)
TABLES = [
    "player_transfers",
    "player_season_stats",
    "team_season_stats",
    "roster",
    "player_id_map",
    "players",
    "teams",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="required — confirms you want to DROP all tables")
    args = parser.parse_args()

    if not args.yes:
        print(f"Would DROP: {', '.join(TABLES)}\nRe-run with --yes to proceed.")
        raise SystemExit(1)

    engine = get_engine()
    with engine.begin() as conn:
        for tbl in TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{tbl}" CASCADE'))
    print(f"Dropped {len(TABLES)} tables. Run `python -m db_client` then `python ingest.py`.")


if __name__ == "__main__":
    main()
