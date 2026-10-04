#!/usr/bin/env bash
# One-time GCP setup. Safe to re-run: each step checks before creating.
# Usage: PROJECT_ID=my-project FACTCHECK_API_KEY=xxx ./scripts/bootstrap_gcp.sh
# Firebase console steps (Auth, App Check, FCM, web app) are manual; see docs/11.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
gcloud config set project "$PROJECT_ID"

echo "== Enabling APIs (takes a few minutes)"
gcloud services enable \
  run.googleapis.com pubsub.googleapis.com firestore.googleapis.com storage.googleapis.com \
  aiplatform.googleapis.com texttospeech.googleapis.com vision.googleapis.com \
  factchecktools.googleapis.com bigquery.googleapis.com bigquerystorage.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com firebase.googleapis.com identitytoolkit.googleapis.com \
  fcm.googleapis.com firebaseappcheck.googleapis.com recaptchaenterprise.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com cloudtrace.googleapis.com \
  iamcredentials.googleapis.com

echo "== Firestore databases"
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --database="(default)" --location="$REGION" --type=firestore-native
gcloud firestore databases describe --database="dev-db" >/dev/null 2>&1 || \
  gcloud firestore databases create --database="dev-db" --location="$REGION" --type=firestore-native

echo "== Vector index on claims.embedding (both databases)"
for DB in "(default)" "dev-db"; do
  gcloud firestore indexes composite create --database="$DB" \
    --collection-group=claims --query-scope=COLLECTION \
    --field-config=field-path=status,order=ASCENDING \
    --field-config='field-path=embedding,vector-config={"dimension":"768","flat":"{}"}' \
    2>/dev/null || echo "   index exists or is building ($DB)"
done

echo "== Buckets"
for B in media outputs eval; do
  gcloud storage buckets describe "gs://${PROJECT_ID}-${B}" >/dev/null 2>&1 || \
    gcloud storage buckets create "gs://${PROJECT_ID}-${B}" --location="$REGION" --uniform-bucket-level-access
done
cat > /tmp/media-lifecycle.json <<'JSON'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 1}}]}
JSON
gcloud storage buckets update "gs://${PROJECT_ID}-media" --lifecycle-file=/tmp/media-lifecycle.json

echo "== Artifact Registry"
gcloud artifacts repositories describe factcheck --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create factcheck --repository-format=docker --location="$REGION"

echo "== Pub/Sub"
gcloud pubsub topics describe check-jobs >/dev/null 2>&1 || gcloud pubsub topics create check-jobs
gcloud pubsub topics describe check-jobs-dlq >/dev/null 2>&1 || gcloud pubsub topics create check-jobs-dlq

echo "== Service accounts"
for SA in api-sa push-sa eval-sa; do
  gcloud iam service-accounts describe "${SA}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "$SA" --display-name="$SA"
done
API_SA="api-sa@${PROJECT_ID}.iam.gserviceaccount.com"
EVAL_SA="eval-sa@${PROJECT_ID}.iam.gserviceaccount.com"
for ROLE in roles/datastore.user roles/storage.objectAdmin roles/aiplatform.user roles/pubsub.publisher \
            roles/bigquery.dataEditor roles/bigquery.jobUser roles/secretmanager.secretAccessor \
            roles/logging.logWriter roles/cloudtrace.agent roles/monitoring.metricWriter \
            roles/firebasecloudmessaging.admin \
            roles/iam.serviceAccountTokenCreator; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${API_SA}" --role="$ROLE" --condition=None >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${EVAL_SA}" --role="$ROLE" --condition=None >/dev/null
done
# ID tokens and App Check tokens are verified with public keys, so no role is needed for that.
# Note: Vision and Text-to-Speech need only the API enabled plus a project-scoped credential.
# serviceAccountTokenCreator lets the API mint signed URLs for audio and card files.

echo "== BigQuery"
bq --location="$REGION" show "${PROJECT_ID}:factcheck" >/dev/null 2>&1 || bq --location="$REGION" mk -d "${PROJECT_ID}:factcheck"
# Tables are created by the backend on startup from schemas in backend/app/observability/bq_schemas.py

echo "== Secrets"
if ! gcloud secrets describe factcheck-tools-api-key >/dev/null 2>&1; then
  gcloud secrets create factcheck-tools-api-key --replication-policy=automatic
fi
if [[ -n "${FACTCHECK_API_KEY:-}" ]]; then
  printf "%s" "$FACTCHECK_API_KEY" | gcloud secrets versions add factcheck-tools-api-key --data-file=-
fi
if ! gcloud secrets describe meta-oembed-token >/dev/null 2>&1; then
  gcloud secrets create meta-oembed-token --replication-policy=automatic
fi
if [[ -n "${META_OEMBED_TOKEN:-}" ]]; then
  printf "%s" "$META_OEMBED_TOKEN" | gcloud secrets versions add meta-oembed-token --data-file=-
fi

echo "== Done. Next: deploy_backend.sh creates the Cloud Run service and the Pub/Sub push subscription."
