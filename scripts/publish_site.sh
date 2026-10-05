#!/usr/bin/env bash
# Publish the static site (dashboard.html + data.json + games/) to S3 and
# invalidate CloudFront. Used by .github/workflows/deploy.yml and for local
# deploys with the aws CLI (the normal path -- see deploy.yml header).
#
#   SITE_BUCKET=bball-dashboard-<acct> CLOUDFRONT_DISTRIBUTION_ID=E... scripts/publish_site.sh
#   scripts/publish_site.sh --dry-run      # show what would be uploaded
#
# Cache-Control (browser + CDN). The CloudFront cache policy
# (Managed-CachingOptimized) ignores query strings, so the dashboard's
# ?v=<generated_at> only busts the BROWSER cache -- every publish therefore
# also invalidates /games/* on the CDN.
#   dashboard.html, data.json, games/seasons.json   5 min   (entry points)
#   games/<season>/index.json, player_logs.json     1 hour  (grow during a live season)
#   games/<season>/g/<id>.json                      30 days (a finished game doesn't change)
# Nothing is deleted from the bucket (insights.json etc. are written elsewhere).
set -euo pipefail
cd "$(dirname "$0")/.."

: "${SITE_BUCKET:?set SITE_BUCKET}"
: "${CLOUDFRONT_DISTRIBUTION_ID:?set CLOUDFRONT_DISTRIBUTION_ID}"
DRY=""
[[ "${1:-}" == "--dry-run" ]] && DRY="--dryrun"
SHORT='public,max-age=300'
MEDIUM='public,max-age=3600'
LONG='public,max-age=2592000'
B="s3://${SITE_BUCKET}"

aws s3 cp dashboard.html "$B/dashboard.html" --cache-control "$SHORT" --content-type 'text/html; charset=utf-8' $DRY
aws s3 cp data.json      "$B/data.json"      --cache-control "$SHORT" --content-type 'application/json' $DRY

if [[ -d games ]]; then
  # box scores: long-lived, only new/changed files are uploaded
  aws s3 sync games "$B/games" --exclude '*' --include '*/g/*.json' \
    --cache-control "$LONG" --content-type 'application/json' $DRY
  # per-season index + logs, then the manifest last (it is what makes a season visible)
  for f in games/*/index.json games/*/player_logs.json; do
    aws s3 cp "$f" "$B/$f" --cache-control "$MEDIUM" --content-type 'application/json' $DRY
  done
  aws s3 cp games/seasons.json "$B/games/seasons.json" --cache-control "$SHORT" --content-type 'application/json' $DRY
fi

if [[ -z "$DRY" ]]; then
  aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths '/' '/dashboard.html' '/data.json' '/games/*' --query 'Invalidation.[Id,Status]' --output text
fi
