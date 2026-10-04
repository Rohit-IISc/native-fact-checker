#!/usr/bin/env bash
# Deploy the eval runner as a Cloud Run Job and schedule it every 3 days at 03:00 IST.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
EVAL_SA="eval-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud run jobs deploy eval-runner --source=. --region="$REGION" \
  --service-account="$EVAL_SA" --task-timeout=3600 --max-retries=0 \
  --command="python" --args="-m,eval.runner" \
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},REGION=${REGION},FIRESTORE_DB=(default)" \
  --set-secrets="FACTCHECK_API_KEY=factcheck-tools-api-key:latest"

gcloud run jobs add-iam-policy-binding eval-runner --region="$REGION" \
  --member="serviceAccount:${EVAL_SA}" --role=roles/run.invoker >/dev/null

if ! gcloud scheduler jobs describe eval-every-3-days --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs create http eval-every-3-days --location="$REGION" \
    --schedule="0 3 */3 * *" --time-zone="Asia/Kolkata" \
    --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/eval-runner:run" \
    --http-method=POST --oauth-service-account-email="$EVAL_SA"
fi
echo "Eval job deployed and scheduled."
