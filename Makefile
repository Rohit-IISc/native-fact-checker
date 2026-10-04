# See CLAUDE.md "Commands". Backend env comes from backend/.env (copy .env.example).
SHELL := /bin/bash
.PHONY: dev dev-offline backend frontend test test-live lint deploy eval check-models install

install:
	cd backend && uv sync
	cd frontend && pnpm install

# Backend on :8080 + frontend on :5173 against the real dev Firestore database ("dev").
dev:
	@trap 'kill 0' EXIT; \
	(cd backend && set -a && [ -f .env ] && . ./.env; set +a; uv run uvicorn app.main:app --reload --port 8080) & \
	(cd frontend && pnpm dev) & \
	wait

# No GCP at all: in-memory store, fake sign-in, recorded model fixtures. For UI work only.
dev-offline:
	@trap 'kill 0' EXIT; \
	(cd backend && STORE=memory AUTH_MODE=dev LLM_MODE=fake PIPELINE_MODE=inline BIGQUERY_ENABLED=0 \
	  uv run uvicorn app.main:app --reload --port 8080) & \
	(cd frontend && VITE_AUTH_MODE=dev pnpm dev) & \
	wait

# Recorded fixtures only; no paid calls.
test:
	cd backend && uv run ruff check . && uv run pytest -q
	cd frontend && pnpm typecheck

# 15 acceptance cases against real models. Costs money: ask Rohit first.
test-live:
	@echo "Live acceptance run costs money. Ask Rohit first, then run: cd backend && uv run pytest -q -m live"

lint:
	cd backend && uv run ruff check .

deploy:
	./scripts/deploy_backend.sh
	./scripts/deploy_frontend.sh

eval:
	PYTHONPATH=backend:. uv run --project backend python -m eval.runner

check-models:
	cd backend && uv run python ../scripts/check_models.py
