"""BigQuery writers for check_runs and model_calls. Best effort; never blocks the user response."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from app.models import CheckRequest, CheckResult
from app.observability.calls import CheckLedger
from app.observability.logging import hash_uid, log_event
from app.settings import get_settings

log = logging.getLogger(__name__)
_bq = None


def _client():
    global _bq
    if _bq is None:
        from google.cloud import bigquery

        _bq = bigquery.Client(project=get_settings().gcp_project)
    return _bq


def check_run_row(req: CheckRequest, result: CheckResult, ledger: CheckLedger, error_code: str | None) -> dict:
    input_types = []
    if req.text:
        input_types.append("text")
    if req.url:
        input_types.append("link")
    input_types += sorted({m.kind for m in req.media})
    labels = [c.label.value for c in result.claims]
    outcomes = sorted({c.panel_outcome.value for c in result.claims})
    return {
        "check_id": req.check_id,
        "uid_hash": hash_uid(req.uid),
        "created_at": datetime.now(UTC).isoformat(),
        "input_types": input_types,
        "platform": None,
        "content_language": result.content_language,
        "n_claims": len(result.claims),
        "cache_tier_hit": result.cache_tier_hit,
        "labels": labels or ([f"NOT_CHECKABLE:{result.non_checkable_type.value}"]
                             if result.non_checkable_type else []),
        "panel_outcome": ",".join(outcomes) or None,
        "degraded": result.degraded,
        "total_latency_ms": result.latency_ms,
        "stage_latency_ms": ledger.stage_latency_ms,
        "total_cost_usd": ledger.total_cost_usd,
        "model_cost_usd": ledger.model_cost_usd,
        "grounding_queries": ledger.grounding_queries,
        "vision_calls": ledger.vision_calls,
        "tts_chars": ledger.tts_chars,
        "error_code": error_code,
        "env": run_env(req.uid),
    }


def run_env(uid: str) -> str:
    """Keeps test traffic out of the dashboard: dev runs (make try/accept/record) and deploy smoke checks."""
    if uid == "deploy-smoke":
        return "smoke"
    return "prod" if os.environ.get("K_SERVICE") else "dev"


async def write_check_run(
    req: CheckRequest, result: CheckResult, ledger: CheckLedger, error_code: str | None = None
) -> None:
    row = check_run_row(req, result, ledger, error_code)
    log_event(log, "check_run", **{k: v for k, v in row.items() if k != "uid_hash"})
    s = get_settings()
    if not s.bigquery_enabled:
        return
    calls = [c.row() for c in ledger.calls]
    import json

    row = {**row, "stage_latency_ms": json.dumps(row["stage_latency_ms"])}

    def _insert() -> None:
        client = _client()
        ds = f"{s.gcp_project}.{s.bigquery_dataset}"
        errors = client.insert_rows_json(f"{ds}.check_runs", [row])
        if calls:
            errors += client.insert_rows_json(f"{ds}.model_calls", calls)
        if errors:
            log_event(log, "bigquery insert errors", logging.WARNING, errors=str(errors)[:1000])

    try:
        await asyncio.to_thread(_insert)
    except Exception as e:  # noqa: BLE001
        log_event(log, "bigquery write failed", logging.WARNING, error=repr(e)[:500])
