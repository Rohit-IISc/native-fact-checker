#!/usr/bin/env bash
# Create or update the dashboard views in BigQuery (scripts/bq_views.sql). Views cost nothing until queried.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
DATASET="${BQ_DATASET:-factcheck}"
sed -e "s/PROJECT\./${PROJECT_ID}./g" -e "s/\.DATASET\./.${DATASET}./g" "$(dirname "$0")/bq_views.sql" \
  | bq query --project_id="$PROJECT_ID" --nouse_legacy_sql --quiet >/dev/null
bq ls --project_id="$PROJECT_ID" "$DATASET" | grep " VIEW " || true
