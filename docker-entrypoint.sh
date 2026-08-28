#!/bin/sh
# Dispatch for the batch image. Usage: docker run <image> <command>
#   migrate  - apply schema.sql to the configured database
#   ingest   - load the season workbook ($WORKBOOK or the bundled one)
#   export   - regenerate data.json; also uploads to s3://$SITE_BUCKET/data.json when SITE_BUCKET is set
#   test     - run the leaderboards sanity script (default)
set -e

cmd="${1:-test}"
shift || true

case "$cmd" in
  migrate)
    exec python -m db_client
    ;;
  ingest)
    exec python ingest.py "$@"
    ;;
  export)
    if [ -n "$SITE_BUCKET" ]; then
      exec python export_dashboard_data.py --out /app/out/data.json --s3-uri "s3://$SITE_BUCKET/data.json" "$@"
    fi
    exec python export_dashboard_data.py --out /app/out/data.json "$@"
    ;;
  test)
    exec python test_analytics.py "$@"
    ;;
  *)
    echo "unknown command: $cmd (expected: migrate|ingest|export|test)" >&2
    exit 2
    ;;
esac
