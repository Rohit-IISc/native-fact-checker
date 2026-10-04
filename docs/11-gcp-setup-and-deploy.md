# 11. GCP setup and deploy

## Terraform vs gcloud scripts (answer to question 33)

| | Terraform | gcloud / firebase CLI scripts |
| --- | --- | --- |
| What it is | You describe the end state in files; Terraform works out what to create or change | A list of commands run top to bottom, like a recipe |
| Pros | Repeatable, shows a diff before changing anything, easy teardown, industry standard | Nothing new to learn, every command is in Google's docs, Claude Code can run and fix one line at a time, fast to write |
| Cons | Learning curve, a state file to store and protect, Firebase parts are awkward in Terraform, slower to set up | Re-running can error on things that already exist (we make each step check first), no automatic teardown |
| Fit for a 7-day build by two people new to both | Poor | Good |

Decision: gcloud and firebase CLI scripts, written so they are safe to re-run. Move to Terraform after the competition if this becomes a product.

## Region

- Cloud Run, Firestore, Cloud Storage, BigQuery, Pub/Sub, Scheduler: `asia-south1` (Mumbai)
- Vertex AI Gemini calls: `global` endpoint (newest Gemini models usually appear there first and some are not in every region). Data at rest stays in Mumbai
- Gemini TTS: use the location the TTS docs list for the chosen model (`global` or `us`)

## One-time setup (Rohit, about 1 hour)

1. Create the GCP project and link billing (competition credits). Set a budget with alerts
2. In the Firebase console, add Firebase to the same project, enable Google sign-in, register the web app, enable App Check with reCAPTCHA Enterprise, enable Cloud Messaging and get the VAPID key
3. Install `gcloud`, `firebase-tools`, `uv`, `node 20+`, `pnpm`, `ffmpeg`
4. `gcloud auth login` and `gcloud auth application-default login`
5. Create a Fact Check Tools API key (APIs and Services, Credentials, restrict to Fact Check Tools API)
6. Optional: Meta app for oEmbed token (developers.facebook.com). Skip if it takes more than 30 minutes; the ladder falls back to Open Graph tags
7. Run `scripts/bootstrap_gcp.sh` with `PROJECT_ID` set
8. Connect the GitHub repo to Cloud Build (console, one time) and create the trigger on push to `main`

## Deploy

- Backend: `scripts/deploy_backend.sh` (Cloud Build builds the image, pushes to Artifact Registry, deploys `factcheck-api` to Cloud Run with the right service account, env vars and secrets)
- Frontend: `scripts/deploy_frontend.sh` (`pnpm build` then `firebase deploy --only hosting`)
- Eval: `scripts/deploy_eval.sh` (Cloud Run Job plus Cloud Scheduler every 3 days)
- CI: `cloudbuild.yaml` runs ruff, pytest, gitleaks, then both deploys on push to `main`
- Firestore indexes and rules: `firebase deploy --only firestore:indexes,firestore:rules`

## Before judging window

- Set Cloud Run min instances to 1 (`--min-instances=1`) from Oct 17 to the end of judging, then back to 0
- Pre-warm: run the demo examples once so they sit in the cache
