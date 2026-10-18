# One image for the API + pipeline service (Cloud Run) and the eval runner (Cloud Run Job).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libraqm0 fonts-noto-core fonts-noto-ui-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /srv
ENV UV_PROJECT_ENVIRONMENT=/srv/.venv UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 APP_ROOT=/srv
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY config/ config/
COPY prompts/ prompts/
COPY backend/ backend/
COPY eval/ eval/
# The daily demo-cache check (scripts/deploy_demo_check.sh) runs the seed script with the acceptance cases.
COPY scripts/seed_demo_cache.py scripts/
COPY tests/acceptance/ tests/acceptance/
ENV PATH="/srv/.venv/bin:$PATH" PYTHONPATH=/srv/backend:/srv
WORKDIR /srv/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --timeout-keep-alive 300"]
