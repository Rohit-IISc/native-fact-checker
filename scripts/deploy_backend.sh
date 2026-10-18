#!/usr/bin/env bash
# Deploy the API + pipeline service, then wire the Pub/Sub push subscription.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
SERVICE="factcheck-api"
API_SA="api-sa@${PROJECT_ID}.iam.gserviceaccount.com"
PUSH_SA="push-sa@${PROJECT_ID}.iam.gserviceaccount.com"
MIN_INSTANCES="${MIN_INSTANCES:-1}"   # 1 during judging (19 Oct to 6 Nov); back to 0 after 7 Nov

# Mount only secrets that have a version (meta-oembed-token stays empty until Instagram/Facebook
# links need it); an empty secret would fail the whole deploy.
SECRETS=""
for pair in FACTCHECK_API_KEY=factcheck-tools-api-key META_OEMBED_TOKEN=meta-oembed-token; do
  if [ -n "$(gcloud secrets versions list "${pair#*=}" --project="$PROJECT_ID" --limit=1 --format='value(name)' 2>/dev/null)" ]; then
    SECRETS="${SECRETS:+$SECRETS,}${pair}:latest"
  else
    echo "Skipping secret ${pair#*=}: no versions"
  fi
done

gcloud run deploy "$SERVICE" \
  --source=. \
  --region="$REGION" \
  --service-account="$API_SA" \
  --allow-unauthenticated \
  --cpu=2 --memory=2Gi --concurrency=10 --timeout=300 \
  --min-instances="$MIN_INSTANCES" --max-instances=20 \
  --set-env-vars="^;^GCP_PROJECT=${PROJECT_ID};REGION=${REGION};FIRESTORE_DB=(default);PIPELINE_MODE=pubsub;STORE=firestore;AUTH_MODE=firebase;LLM_MODE=gemini;BIGQUERY_ENABLED=1;APP_CHECK_ENFORCE=true;LOG_LEVEL=INFO;PUSH_SA=${PUSH_SA};PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://chckr.web.app};CORS_ORIGINS=${CORS_ORIGINS:-https://chckr.web.app,https://chckr.firebaseapp.com,https://${PROJECT_ID}.web.app,https://${PROJECT_ID}.firebaseapp.com}" \
  --project="$PROJECT_ID" \
  --set-secrets="$SECRETS"

# Large shares (over Cloud Run's 32 MB request limit) are PUT straight into the media bucket from the PWA.
gcloud storage buckets update "gs://${PROJECT_ID}-media" --cors-file="$(dirname "$0")/media_cors.json" >/dev/null

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
  # Repeat the auth flags: an update with only --push-endpoint drops the OIDC token, and every push
  # then fails with 401 at /internal/pipeline.
  gcloud pubsub subscriptions update check-jobs-push --push-endpoint="${URL}/internal/pipeline" \
    --push-auth-service-account="$PUSH_SA" --push-auth-token-audience="${URL}/internal/pipeline"
fi
# Pub/Sub's service agent must be able to publish to the DLQ and ack the source subscription:
PNUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
PS_AGENT="service-${PNUM}@gcp-sa-pubsub.iam.gserviceaccount.com"
gcloud pubsub topics add-iam-policy-binding check-jobs-dlq --member="serviceAccount:${PS_AGENT}" --role=roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions add-iam-policy-binding check-jobs-push --member="serviceAccount:${PS_AGENT}" --role=roles/pubsub.subscriber >/dev/null
echo "Backend deployed."
