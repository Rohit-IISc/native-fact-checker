# See CLAUDE.md "Commands".
# Backend config precedence: environment variables (Codespaces secrets) > backend/.env (optional,
# gitignored) > backend/.env.defaults. Frontend: VITE_* env vars > frontend/.env.development.
SHELL := /bin/bash
.PHONY: load-test deploy-ops dev dev-offline backend frontend test test-live lint deploy eval check-models install try accept record smoke
# Free text goes to the CLI through the environment so quotes and commas survive.
export TEXT URL

install:
	cd backend && uv sync
	cd frontend && pnpm install

backend/.venv:
	cd backend && uv sync

frontend/node_modules:
	cd frontend && pnpm install

# Backend on :8080 (reload) + frontend on :5173, both on 0.0.0.0, prefixed logs (Procfile, honcho).
# Real dev Firestore database (FIRESTORE_DB). One Ctrl+C stops both.
# Needs Application Default Credentials: gcloud auth application-default login
dev: backend/.venv frontend/node_modules
	uv run --project backend honcho -f Procfile start

# No GCP at all: in-memory store, fake sign-in, recorded model fixtures. For UI work only.
dev-offline: backend/.venv frontend/node_modules
	@trap 'kill 0' EXIT; \
	(cd backend && FACTCHECK_SKIP_ENV_FILES=1 STORE=memory AUTH_MODE=dev LLM_MODE=fake PIPELINE_MODE=inline BIGQUERY_ENABLED=0 \
	  uv run uvicorn app.main:app --reload --port 8080) & \
	(cd frontend && VITE_AUTH_MODE=dev pnpm dev) & \
	wait

# No paid calls: unit tests + replay of recorded model outputs in backend/tests/fixtures/.
test:
	cd backend && uv run ruff check . && uv run pytest -q
	cd frontend && pnpm typecheck

# Full pipeline in-process, no UI. make try TEXT="..." | FILE=path | URL=...
#   STAGE=extract (one stage)  TRY_STORE=firestore (real cache + progress docs)  FAKE=1 (no paid calls)
# Saves every run to runs/{timestamp}.json.
try: backend/.venv
	@cd backend && uv run python -m app.devtools.try_cmd \
	  $(if $(TEXT),--text "$$TEXT") $(if $(FILE),--file "$(abspath $(FILE))") $(if $(URL),--url "$$URL") \
	  $(if $(STAGE),--stage $(STAGE)) $(if $(TRY_STORE),--store $(TRY_STORE)) $(if $(FAKE),--fake) $(ARGS)

# Every case in tests/acceptance/ (real models, ~$0.10-0.15 per case). CASE=substring, FAKE=1,
# REPEAT=N runs each case N times and reports pass rates (single runs are noisy).
accept: backend/.venv
	@cd backend && uv run python -m app.devtools.accept $(if $(CASE),--case "$(CASE)") $(if $(FAKE),--fake) \
	  $(if $(REPEAT),--repeat $(REPEAT)) $(ARGS)

# Refresh backend/tests/fixtures/ from real model calls (acceptance inputs), for make test.
record: backend/.venv
	@cd backend && uv run python -m app.devtools.accept --record $(if $(CASE),--case "$(CASE)") $(ARGS)

# 15 acceptance cases against real models. Costs money: ask Rohit first.
test-live:
	@echo "Live acceptance run costs money. Ask Rohit first, then run: cd backend && uv run pytest -q -m live"

lint:
	cd backend && uv run ruff check .

# Real checks against the deployed service (production DB, cleaned up afterwards). About $0.40.
smoke:
	cd backend && PYTHONPATH=. uv run python ../scripts/smoke_prod.py

# Production load test: 3, 5 and 10 checks at once (about 2.50 USD). WAVES=3,5 to change.
load-test:
	cd backend && PYTHONPATH=. uv run python ../scripts/load_test.py $(if $(WAVES),--waves $(WAVES))

# PROJECT_ID defaults to GCP_PROJECT from backend/.env.defaults.
deploy: export PROJECT_ID ?= $(shell sed -n 's/^GCP_PROJECT=\([^ ]*\).*/\1/p' backend/.env.defaults)
deploy:
	@test -n "$$PROJECT_ID" || (echo "Set PROJECT_ID" && exit 1)
	./scripts/deploy_backend.sh
	./scripts/deploy_frontend.sh

# Eval job + its every-3-days schedule, dashboard views, alerts (Day 6). Re-runnable.
deploy-ops: export PROJECT_ID ?= $(shell sed -n 's/^GCP_PROJECT=\([^ ]*\).*/\1/p' backend/.env.defaults)
deploy-ops:
	@test -n "$$PROJECT_ID" || (echo "Set PROJECT_ID" && exit 1)
	./scripts/deploy_eval.sh
	./scripts/create_bq_views.sh
	./scripts/create_alerts.sh

eval:
	PYTHONPATH=backend:. uv run --project backend python -m eval.runner $(ARGS)

check-models:
	cd backend && uv run python ../scripts/check_models.py
