# CLAUDE.md: Native-Language Fact Checker (AI Builder Cup, team Frugalists)

You are building a working prototype of a fact checker that answers in the user's own language, as text and audio. A user shares a WhatsApp forward or social media post (image, video, audio, text, screenshot or link) into our web app. The app checks it and returns a verdict with credible sources, in the language of the forwarded content.

Read this file fully, then read the docs in `docs/` in numeric order before writing code. `docs/16-decisions-log.md` is the source of truth when anything conflicts. The old "Problem Statement and Solution Skeleton" doc is superseded by this folder.

## Dates

- Today the build starts: Sun Oct 4, 2026
- Working prototype, deployed: Sun Oct 11, 2026
- Testing and fixes: Oct 12 to Oct 17
- Competition submission: Sun Oct 18, 2026

Follow `docs/12-build-plan.md` day by day. If a day slips, cut scope in the order listed there, never quality of verdicts.

## What we are building (prototype scope)

In scope:
- Android-first PWA on Firebase Hosting with Web Share Target (appears in the Android share sheet, including WhatsApp)
- Mandatory Google sign-in, 10 checks per user per day, check history
- Inputs: text, up to 10 images, one video or audio up to 3 minutes, links. Max 50 MB per share
- Two-tier cache shared by all users (exact hash, then semantic match)
- Information extractor (Gemini Flash, multimodal) that outputs each claim in the original language and in English
- Fixed parallel fan-out to four sub-agents: web search, fact-check sites, source credibility, media provenance
- Evidence packager, then a review panel: Judge (Gemini Pro) plus Critic (Gemini Pro). A split ends in "Not enough evidence" with all evidence for and against shown
- Answer in the content's language: text (plus English), Gemini TTS audio, correction card image, shareable result page
- Live progress screen, push notification when the user has left the screen
- Scheduled evaluation every 3 days, BigQuery observability, cost per check

Out of scope for the prototype: bank SMS and phishing, scam checker agent, human fact-checker escalation, iOS share target, native mobile apps, public B2B API (documented only), LLM-based routing of sub-agents. Satellite verifier is a stretch goal (`docs/15-satellite-verifier-stretch.md`), built only after Oct 11 if everything else passes.

## Non-negotiable rules

1. No TRUE, FALSE, MISLEADING or SCAM verdict without credible sources. The source policy in `docs/09-source-credibility.md` is enforced in code (`source_policy.py`), not only in prompts. If the policy fails, the verdict becomes NOT_ENOUGH_EVIDENCE.
2. Social media posts, forums and video platforms are never a primary source (X, Reddit, Facebook, Instagram, YouTube uploads by non-official channels, Telegram, ShareChat, WhatsApp).
3. The Judge sees only the evidence pack, never the raw post's persuasion. The Critic sees the evidence pack and the Judge's output.
4. Every verdict lists evidence for and evidence against, even when confident.
5. Raw user media is deleted within 24 hours (GCS lifecycle). We store hashes, extracted claims and verdicts only.
6. All model IDs come from `config/models.yaml`. Never hard-code a model name in Python.
7. All prompts live in `prompts/` as files and are loaded at runtime with a version string. Never inline long prompts in code.
8. Secrets live in Secret Manager. Nothing secret goes in the repo. The repo will be public for judging.
9. Every pipeline stage updates the check's progress in Firestore so the live screen moves.
10. Same rules for every claim regardless of topic or political side. No partisan labels on sources.

## Stack

- Backend: Python 3.12, FastAPI, Google Gen AI SDK (`google-genai`) on Vertex AI, Pydantic v2, `uv` for deps, `ruff` and `pytest`
- Frontend: React + Vite + TypeScript (strict), `vite-plugin-pwa`, Firebase JS SDK (Auth, Firestore, Messaging, App Check), i18n with `i18next`
- GCP: Cloud Run (asia-south1), Pub/Sub, Firestore Native (asia-south1, with vector search), Cloud Storage, Vertex AI (Gemini via `global` endpoint), Gemini TTS, Cloud Vision, Fact Check Tools API, BigQuery, Secret Manager, Cloud Scheduler, Cloud Build, Artifact Registry, Firebase Hosting/Auth/FCM/App Check
- Infra: plain `gcloud` and `firebase` CLI scripts in `scripts/` (no Terraform; see `docs/11-gcp-setup-and-deploy.md`)

## Repo layout to create

```
repo/
  CLAUDE.md                 (this file, copied to repo root)
  docs/  prompts/  config/  (copied from this folder)
  backend/
    pyproject.toml
    app/
      main.py               FastAPI app: public API + /internal/pipeline (Pub/Sub push)
      settings.py           env + config/*.yaml loader
      auth.py               Firebase ID token + App Check verification
      quota.py              per-user daily limit (Firestore transaction)
      models.py             Pydantic models (start from schemas/models.py)
      intake/               upload handling, hashing, link fetch ladder, SSRF guard
      cache/                tier 1 exact hash, tier 2 vector search, near-match check
      pipeline/             run_check(): stage runner, deadlines, progress updates
      agents/               Gemini agents (Gen AI SDK): extractor, web_search, factcheck_sites,
                            source_credibility, media_provenance, packager, judge, critic, composer
      verify/source_policy.py
      output/               tts.py, card.py (Pillow + libraqm + Noto), notify.py (FCM)
      observability/        structured logging, BigQuery check_runs writer, cost calc
      prompts.py            prompt loader with versions
    tests/
  frontend/
    src/  public/manifest.webmanifest  (share_target)  src/sw.ts
  eval/
    runner.py               Cloud Run Job: benchmark + regression
    datasets/
  scripts/                  bootstrap_gcp.sh, deploy_backend.sh, deploy_frontend.sh, seed_sources.py
  .github/ or cloudbuild.yaml
```

## Commands (define these as you build)

- `make dev` runs backend on :8080 and frontend on :5173 against the real dev Firestore database named `dev-db` (database IDs need at least 4 characters) (the Firestore emulator does not support vector search, so we do not use it)
- `make test` runs pytest with recorded model fixtures (no paid calls)
- `make test-live` runs the 15 acceptance cases in `tests/acceptance-cases.md` against real models (costs money, ask Rohit first)
- `make deploy` runs scripts/deploy_backend.sh then scripts/deploy_frontend.sh
- `make eval` runs the eval job locally

## How to work

- Keep `docs/PROGRESS.md` up to date. After finishing any task, and before Rohit stops working, update it with: current build-plan day, what's done, what's in progress (file and function), what's broken, the exact next step, and the latest `make accept` results. Commit it together with the code it describes.
- Build vertically: one input type working end to end before adding the next. Day 1 target is text-only end to end with a stub verdict.
- Put a deadline on every external call. Use `asyncio.wait_for` with values from `config/limits.yaml`.
- Every model call returns structured JSON validated by Pydantic. On validation failure retry once with the error appended, then fail the stage gracefully.
- Log every model call with: check_id, stage, model, input tokens, output tokens, latency, grounding queries. Cost is computed from `config/models.yaml` prices.
- Write tests for: source policy, cache key logic, quota, link fetch ladder (with mocked HTTP), verdict merge logic for the panel, SSRF guard.
- Do not add dependencies that need paid third-party APIs. Everything Google.
- Ask Rohit before: creating GCP resources that cost money beyond the bootstrap script, changing the verdict scale, changing the source policy, or making the repo public.
- Before calling the deploy done, confirm model IDs exist in Vertex AI (`scripts/check_models.py`) because Gemini versions change often. Current candidates are in `config/models.yaml`.

## Definition of done for Oct 11

- A signed-in Android user shares a WhatsApp image to the PWA and gets a native-language verdict with audio, sources and a correction card in under 90 seconds
- Same for a link (news article, X post, YouTube) and a short video
- A repeat share of the same or slightly edited content returns from cache in under 5 seconds
- Hindi, Tamil, Kannada, Indonesian and English all pass the acceptance cases
- Deployed on GCP with a public URL, Cloud Build deploys on push to main
- BigQuery shows latency and cost per check; eval job has run once and stored a baseline
