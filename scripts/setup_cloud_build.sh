#!/usr/bin/env bash
# One-time setup for "deploy on push" (docs/11): build service account, the PWA's Firebase keys in Secret
# Manager, the GitHub connection and the trigger. Re-runnable; each step skips what already exists.
#
# The GitHub connection needs a person: the first run prints a link; open it, authorize Cloud Build and
# install the Cloud Build GitHub app on Rohit-IISc/native-fact-checker, then run this script again.
#
#   PROJECT_ID=ai-builder-2026 scripts/setup_cloud_build.sh
# Deploys come from main (decision 44); BRANCH overrides it.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="asia-south1"
REPO_OWNER="${REPO_OWNER:-Rohit-IISc}"
REPO_NAME="${REPO_NAME:-native-fact-checker}"
BRANCH="${BRANCH:-main}"
SA="build-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# 1. Build service account with only what the deploy scripts use.
gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud iam service-accounts create build-sa --project="$PROJECT_ID" --display-name="Cloud Build deploys"
for role in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor roles/storage.admin \
            roles/artifactregistry.writer roles/secretmanager.secretAccessor roles/secretmanager.viewer \
            roles/firebasehosting.admin roles/firebaserules.admin roles/datastore.indexAdmin roles/pubsub.editor \
            roles/logging.logWriter roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" \
    --condition=None >/dev/null
done
echo "build-sa ready"

# 2. The PWA's Firebase config, from this shell (Codespaces secrets), into Secret Manager.
for pair in vite-firebase-api-key=VITE_FIREBASE_API_KEY vite-firebase-app-id=VITE_FIREBASE_APP_ID \
            vite-firebase-vapid-key=VITE_FIREBASE_VAPID_KEY vite-recaptcha-site-key=VITE_RECAPTCHA_ENTERPRISE_SITE_KEY; do
  name="${pair%%=*}" var="${pair#*=}"
  if ! gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    : "${!var:?$var is not set in this shell}"
    printf '%s' "${!var}" | gcloud secrets create "$name" --project="$PROJECT_ID" --replication-policy=automatic \
      --data-file=- >/dev/null
    echo "secret $name created"
  fi
done

# 3. GitHub connection (2nd gen). Needs one browser authorization. Cloud Build's service agent stores the
#    GitHub token in Secret Manager, so it needs secretmanager.admin (Google's documented requirement).
NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None >/dev/null \
  --member="serviceAccount:service-${NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" --role=roles/secretmanager.admin
if ! gcloud builds connections describe github --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud builds connections create github github --region="$REGION" --project="$PROJECT_ID"
fi
STAGE="$(gcloud builds connections describe github --region="$REGION" --project="$PROJECT_ID" \
  --format='value(installationState.stage)')"
if [ "$STAGE" != "COMPLETE" ]; then
  echo "GitHub connection not authorized yet. Open this link, authorize, install the app on $REPO_OWNER/$REPO_NAME:"
  gcloud builds connections describe github --region="$REGION" --project="$PROJECT_ID" \
    --format='value(installationState.actionUri)'
  echo "Then run this script again."
  exit 0
fi
gcloud builds repositories describe "$REPO_NAME" --connection=github --region="$REGION" --project="$PROJECT_ID" \
  >/dev/null 2>&1 || gcloud builds repositories create "$REPO_NAME" --connection=github --region="$REGION" \
  --project="$PROJECT_ID" --remote-uri="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"

# 4. Trigger: test and deploy on push to BRANCH.
REPO="projects/${PROJECT_ID}/locations/${REGION}/connections/github/repositories/${REPO_NAME}"
if gcloud builds triggers describe deploy-on-push --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud builds triggers delete deploy-on-push --region="$REGION" --project="$PROJECT_ID" --quiet
fi
gcloud builds triggers create github --name=deploy-on-push --region="$REGION" --project="$PROJECT_ID" \
  --repository="$REPO" --branch-pattern="^${BRANCH}\$" --build-config=cloudbuild.yaml \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${SA}"
echo "Trigger deploy-on-push: every push to $BRANCH tests and deploys."
