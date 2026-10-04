# See CLAUDE.md "Commands".
# Backend config precedence: environment variables (Codespaces secrets) > backend/.env (optional,
# gitignored) > backend/.env.defaults. Frontend: VITE_* env vars > frontend/.env.development.
SHELL := /bin/bash
.PHONY: dev dev-offline backend frontend test test-live lint deploy eval check-models install

install:
	cd backend && uv sync
	cd frontend && pnpm install

backend/.venv:
	cd backend && uv sync

frontend/node_modules:
	cd frontend && pnpm install

# Backend on :8080 + frontend on :5173 against the real dev Firestore database (FIRESTORE_DB).
# Needs Application Default Credentials: gcloud auth application-default login
dev: backend/.venv frontend/node_modules
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080) & \
	(cd frontend && pnpm dev --host 0.0.0.0) & \
	wait

# No GCP at all: in-memory store, fake sign-in, recorded model fixtures. For UI work only.
dev-offline: backend/.venv frontend/node_modules
	@trap 'kill 0' EXIT; \
	(cd backend && FACTCHECK_SKIP_ENV_FILES=1 STORE=memory AUTH_MODE=dev LLM_MODE=fake PIPELINE_MODE=inline BIGQUERY_ENABLED=0 \
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
