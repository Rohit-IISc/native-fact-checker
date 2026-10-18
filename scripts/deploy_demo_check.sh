#!/usr/bin/env bash
# Daily check of the seeded demo cache during judging: a Cloud Run Job runs seed_demo_cache.py --check at
# 06:00 IST, re-seeds any demo share the cache no longer answers, and pins every demo verdict. Runs as api-sa
# (it writes the production cache like the API does). Demo media comes from gs://${PROJECT_ID}-eval/demo-media/.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
SA="api-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud run jobs deploy demo-cache-check --source=. --region="$REGION" \
  --service-account="$SA" --task-timeout=3600 --max-retries=0 --cpu=2 --memory=2Gi \
  --command="python" --args="/srv/scripts/seed_demo_cache.py,--check" \
  --set-env-vars="^;^GCP_PROJECT=${PROJECT_ID};REGION=${REGION};STORE=firestore;FIRESTORE_DB=(default);BIGQUERY_ENABLED=0;LLM_MODE=gemini;LOG_LEVEL=INFO" \
  --set-secrets="FACTCHECK_API_KEY=factcheck-tools-api-key:latest"

gcloud run jobs add-iam-policy-binding demo-cache-check --region="$REGION" \
  --member="serviceAccount:${SA}" --role=roles/run.invoker >/dev/null

VERB=create
gcloud scheduler jobs describe demo-cache-check-daily --location="$REGION" >/dev/null 2>&1 && VERB=update
gcloud scheduler jobs "$VERB" http demo-cache-check-daily --location="$REGION" \
  --schedule="0 6 * * *" --time-zone="Asia/Kolkata" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/demo-cache-check:run" \
  --http-method=POST --oauth-service-account-email="$SA"
echo "Demo cache check deployed and scheduled daily at 06:00 IST."
