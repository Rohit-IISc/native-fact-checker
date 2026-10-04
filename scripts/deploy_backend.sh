#!/usr/bin/env bash
# Deploy the API + pipeline service, then wire the Pub/Sub push subscription.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
SERVICE="factcheck-api"
API_SA="api-sa@${PROJECT_ID}.iam.gserviceaccount.com"
PUSH_SA="push-sa@${PROJECT_ID}.iam.gserviceaccount.com"
MIN_INSTANCES="${MIN_INSTANCES:-0}"   # set to 1 during judging

gcloud run deploy "$SERVICE" \
  --source=. \
  --region="$REGION" \
  --service-account="$API_SA" \
  --allow-unauthenticated \
  --cpu=2 --memory=2Gi --concurrency=10 --timeout=300 \
  --min-instances="$MIN_INSTANCES" --max-instances=20 \
  --set-env-vars="^;^GCP_PROJECT=${PROJECT_ID};REGION=${REGION};FIRESTORE_DB=(default);PIPELINE_MODE=pubsub;STORE=firestore;AUTH_MODE=firebase;LLM_MODE=gemini;BIGQUERY_ENABLED=1;PUSH_SA=${PUSH_SA};PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://${PROJECT_ID}.web.app};CORS_ORIGINS=${CORS_ORIGINS:-https://${PROJECT_ID}.web.app,https://${PROJECT_ID}.firebaseapp.com}" \
  --set-secrets="FACTCHECK_API_KEY=factcheck-tools-api-key:latest,META_OEMBED_TOKEN=meta-oembed-token:latest"

URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
echo "Service URL: $URL"

gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:${PUSH_SA}" --role=roles/run.invoker >/dev/null

if ! gcloud pubsub subscriptions describe check-jobs-push >/dev/null 2>&1; then
  gcloud pubsub subscriptions create check-jobs-push \
    --topic=check-jobs \
    --push-endpoint="${URL}/internal/pipeline" \
    --push-auth-service-account="$PUSH_SA" \
    --push-auth-token-audience="${URL}/internal/pipeline" \
    --ack-deadline=600 \
    --dead-letter-topic=check-jobs-dlq --max-delivery-attempts=5
else
  gcloud pubsub subscriptions update check-jobs-push --push-endpoint="${URL}/internal/pipeline"
fi
# Pub/Sub's service agent must be able to publish to the DLQ and ack the source subscription:
PNUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
PS_AGENT="service-${PNUM}@gcp-sa-pubsub.iam.gserviceaccount.com"
gcloud pubsub topics add-iam-policy-binding check-jobs-dlq --member="serviceAccount:${PS_AGENT}" --role=roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions add-iam-policy-binding check-jobs-push --member="serviceAccount:${PS_AGENT}" --role=roles/pubsub.subscriber >/dev/null
echo "Backend deployed."
