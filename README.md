# Native-Language Fact Checker

Team Frugalists, AI Builder Cup 2026. Share a WhatsApp forward or social post into the PWA and get a
verdict with credible sources, in the language of the content, as text and audio.

Start with [`CLAUDE.md`](CLAUDE.md), then `docs/` in numeric order. `docs/16-decisions-log.md` wins on conflicts.

## Layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI API + pipeline (Python 3.12, `uv`). One image serves `/v1` and `/internal/pipeline` |
| `frontend/` | React + Vite + TS PWA with Web Share Target, Firebase Auth / Firestore / App Check, i18next (en, hi, ta, kn, id) |
| `config/` | Models and prices, limits, languages, fan-out agents, source tiers |
| `prompts/` | All model prompts, versioned, loaded at runtime |
| `scripts/` | GCP bootstrap, deploy scripts, model check |
| `eval/` | Eval runner (Cloud Run Job) |
| `docs/` | Architecture docs; `docs/architecture/` holds the original folder README and schema |

## Run locally

The devcontainer (`.devcontainer/`) works in GitHub Codespaces or VS Code locally.

```bash
gcloud auth application-default login   # once per container (the gcloud volume keeps it)
make dev           # backend :8080 + PWA :5173 against the dev Firestore DB and real Gemini
make dev-offline   # no GCP: in-memory store, fake sign-in, recorded model fixtures
make test          # ruff + pytest (no paid calls) + frontend typecheck
```

Configuration:

| Where | Backend | Frontend |
| --- | --- | --- |
| Secrets | Codespaces secrets (`FACTCHECK_API_KEY`); Secret Manager in Cloud Run | Codespaces secrets (`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_APP_ID`, `VITE_FIREBASE_VAPID_KEY`, `VITE_RECAPTCHA_ENTERPRISE_SITE_KEY`) |
| Optional local override (gitignored) | `backend/.env` | `frontend/.env.development.local` |
| Committed non-secret defaults | `backend/.env.defaults` | `frontend/.env.development` |

Precedence is top to bottom: environment variables win, then the override file, then the defaults.
In Codespaces (`CODESPACES=true`) the backend sets `PUBLIC_BASE_URL` to the forwarded URL of port 5173
and adds it to `CORS_ORIGINS`; Vite accepts the forwarded host. Add that host to Firebase Auth
authorized domains for Google sign-in. Env files are excluded from the Cloud Run image.

## Build status

| Day | Status |
| --- | --- |
| 0 Setup | Code done: backend skeleton, `/healthz`, PWA shell with Google sign-in, share target, Dockerfile, Firebase config. Manual GCP and Firebase console steps still to do (docs/11) |
| 1 Text lane | Done in code: paste text → quota → tier 1 text/URL cache → extractor (Gemini Flash, structured output) → stub verdict through panel and source policy → Firestore progress → live screen → result, history, public result page. Measuring extraction latency on 10 videos is still to do |
| 2+ | Not started: media upload, link fetch ladder, sub-agents, panel, composer, TTS, card, push, eval |

The source policy (`backend/app/verify/source_policy.py`) and the panel merge logic (`backend/app/pipeline/panel.py`)
already exist as plain code with unit tests, so Day 4 only adds the Judge and Critic model calls.
