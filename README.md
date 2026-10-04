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

```bash
make install
make dev-offline   # no GCP: in-memory store, fake sign-in, recorded model fixtures
make dev           # real dev Firestore + Gemini; needs backend/.env and frontend/.env.local (see .env.example files)
make test          # ruff + pytest (no paid calls) + frontend typecheck
```

## Build status

| Day | Status |
| --- | --- |
| 0 Setup | Code done: backend skeleton, `/healthz`, PWA shell with Google sign-in, share target, Dockerfile, Firebase config. Manual GCP and Firebase console steps still to do (docs/11) |
| 1 Text lane | Done in code: paste text → quota → tier 1 text/URL cache → extractor (Gemini Flash, structured output) → stub verdict through panel and source policy → Firestore progress → live screen → result, history, public result page. Measuring extraction latency on 10 videos is still to do |
| 2+ | Not started: media upload, link fetch ladder, sub-agents, panel, composer, TTS, card, push, eval |

The source policy (`backend/app/verify/source_policy.py`) and the panel merge logic (`backend/app/pipeline/panel.py`)
already exist as plain code with unit tests, so Day 4 only adds the Judge and Critic model calls.
