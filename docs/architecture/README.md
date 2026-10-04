# Native-Language Fact Checker: architecture folder

Team Frugalists, AI Builder Cup 2026. Prepared Oct 4, 2026.

## How to use this folder

1. Create an empty GitHub repo and copy this whole folder into it
2. Move `CLAUDE.md` to the repo root (it already sits there if you copy the folder as the root), move `scripts/cloudbuild.yaml` to the root
3. Open the repo in Claude Code and say: "Read CLAUDE.md and the docs in order, then start Day 0 of docs/12-build-plan.md"
4. Do the manual Day 0 steps in `docs/11-gcp-setup-and-deploy.md` (project, billing, Firebase console, API key)

## Contents

| Path | What |
| --- | --- |
| `CLAUDE.md` | Instructions for Claude Code: scope, rules, stack, repo layout, definition of done |
| `docs/01` to `docs/16` | Scope, architecture, pipeline and agents, cache, data model, API, frontend, security and privacy, source policy, evaluation, GCP setup, build plan, cost, submission checklist, satellite stretch goal, decisions log |
| `prompts/` | All model prompts, versioned |
| `config/` | Models and prices, limits, languages, fan-out agents, source tiers |
| `schemas/models.py` | Pydantic models for every stage |
| `scripts/` | GCP bootstrap, deploy scripts, model check, Cloud Build config |
| `tests/acceptance-cases.md` | The 15 cases that define "working" |

## Key dates

Prototype Oct 11, test week Oct 12 to 17, submission Oct 18, 2026.
