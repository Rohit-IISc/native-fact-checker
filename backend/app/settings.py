"""Environment settings and config/*.yaml loader.

Config files live at the repo root (`config/`, `prompts/`). In the container they
are copied next to the app; APP_ROOT overrides discovery.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _find_root() -> Path:
    if env := os.environ.get("APP_ROOT"):
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "models.yaml").exists():
            return parent
    raise RuntimeError("Could not find config/models.yaml; set APP_ROOT")


@dataclass(frozen=True)
class Settings:
    root: Path
    gcp_project: str
    region: str
    vertex_location: str        # overrides config/models.yaml vertex.location when set
    firestore_db: str
    firebase_project_id: str
    # inline: run the pipeline in-process after POST /v1/checks (local). pubsub: publish to check-jobs.
    pipeline_mode: str
    # firestore | memory (memory is for tests and offline UI work only)
    store: str
    # firebase | dev ("Bearer dev:<uid>" accepted, App Check skipped). Never dev in Cloud Run.
    auth_mode: str
    # false only for local dev until the App Check debug token is registered; always true in Cloud Run
    app_check_enforce: bool
    # gemini | fake (recorded fixtures, no paid calls)
    llm_mode: str
    push_sa: str
    pubsub_topic: str
    public_base_url: str
    cors_origins: list[str] = field(default_factory=list)
    factcheck_api_key: str = ""
    media_bucket: str = ""
    outputs_bucket: str = ""
    eval_bucket: str = ""
    bigquery_dataset: str = "factcheck"
    bigquery_enabled: bool = False
    log_level: str = "INFO"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"


def _env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser: comments, blank lines, `export`, quoted values, inline ` #` comments."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"') and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_env_files(backend_dir: Path | None = None) -> None:
    """Fill os.environ in precedence order: real environment variables (Codespaces secrets,
    Cloud Run), then backend/.env (gitignored, optional), then backend/.env.defaults.
    setdefault never overrides a value that is already set. FACTCHECK_SKIP_ENV_FILES=1 skips this
    (tests)."""
    if os.environ.get("FACTCHECK_SKIP_ENV_FILES") == "1":
        return
    backend_dir = backend_dir or Path(__file__).resolve().parent.parent
    for name in (".env", ".env.defaults"):
        path = backend_dir / name
        if path.is_file():
            for key, value in _parse_env_file(path).items():
                os.environ.setdefault(key, value)


def codespaces_url(port: int) -> str | None:
    """Public forwarded URL for a port when running in GitHub Codespaces."""
    if os.environ.get("CODESPACES") != "true":
        return None
    name = os.environ.get("CODESPACE_NAME")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    return f"https://{name}-{port}.{domain}" if name else None


@lru_cache
def get_settings() -> Settings:
    load_env_files()
    project = os.environ.get("GCP_PROJECT", "")
    # In Codespaces the browser reaches the PWA through the forwarded URL of the Vite port.
    frontend_url = codespaces_url(int(os.environ.get("FRONTEND_PORT", "5173")))
    default_public = frontend_url or "http://localhost:5173"
    cors = _env_list("CORS_ORIGINS", "http://localhost:5173")
    if frontend_url and frontend_url not in cors:
        cors.append(frontend_url)
    return Settings(
        root=_find_root(),
        gcp_project=project,
        region=os.environ.get("REGION", "asia-south1"),
        vertex_location=os.environ.get("VERTEX_LOCATION", ""),
        firestore_db=os.environ.get("FIRESTORE_DB", "dev-db"),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", project),
        pipeline_mode=os.environ.get("PIPELINE_MODE", "inline"),
        store=os.environ.get("STORE", "firestore"),
        auth_mode=os.environ.get("AUTH_MODE", "firebase"),
        app_check_enforce=os.environ.get("APP_CHECK_ENFORCE", "true").lower() not in ("0", "false", "no"),
        llm_mode=os.environ.get("LLM_MODE", "gemini"),
        push_sa=os.environ.get("PUSH_SA", ""),
        pubsub_topic=os.environ.get("PUBSUB_TOPIC", "check-jobs"),
        public_base_url=(frontend_url or os.environ.get("PUBLIC_BASE_URL") or default_public).rstrip("/"),
        cors_origins=cors,
        factcheck_api_key=os.environ.get("FACTCHECK_API_KEY", ""),
        media_bucket=os.environ.get("MEDIA_BUCKET", f"{project}-media" if project else ""),
        outputs_bucket=os.environ.get("OUTPUTS_BUCKET", f"{project}-outputs" if project else ""),
        eval_bucket=os.environ.get("EVAL_BUCKET", f"{project}-eval" if project else ""),
        bigquery_dataset=os.environ.get("BQ_DATASET") or os.environ.get("BIGQUERY_DATASET") or "factcheck",
        bigquery_enabled=os.environ.get("BIGQUERY_ENABLED", "1" if project else "0") == "1",
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )


def _load_yaml(name: str) -> dict[str, Any]:
    path = get_settings().config_dir / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass(frozen=True)
class AppConfig:
    models: dict[str, Any]
    limits: dict[str, Any]
    languages: dict[str, Any]
    agents: dict[str, Any]
    source_tiers: dict[str, Any]

    def model_for_stage(self, stage: str) -> dict[str, Any]:
        """Model entry for a pipeline stage, via stage_models -> models."""
        key = self.models["stage_models"][stage]
        return {"key": key, **self.models["models"][key]}

    def timeout(self, name: str) -> float:
        return float(self.limits["timeouts_s"][name])

    def extraction_timeout(self, media_seconds: float) -> float:
        t = self.limits["timeouts_s"]
        return float(t["extraction_base"]) + float(t["extraction_per_media_second"]) * media_seconds

    def total_budget(self, media_seconds: float) -> float:
        base = float(self.limits["timeouts_s"]["total_base"])
        return base + (self.extraction_timeout(media_seconds) - float(self.limits["timeouts_s"]["extraction_base"]))


@lru_cache
def get_config() -> AppConfig:
    # Runtime overrides from Firestore config/{models,limits,flags} are applied by the eval runner
    # and an admin endpoint later; YAML is the baseline.
    return AppConfig(
        models=_load_yaml("models.yaml"),
        limits=_load_yaml("limits.yaml"),
        languages=_load_yaml("languages.yaml"),
        agents=_load_yaml("agents.yaml"),
        source_tiers=_load_yaml("source_tiers.yaml"),
    )
