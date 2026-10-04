"""BigQuery table schemas (docs/05). Tables are created on startup if missing."""
from __future__ import annotations

import logging

from app.settings import get_settings

log = logging.getLogger(__name__)

CHECK_RUNS = [
    ("check_id", "STRING", "REQUIRED"),
    ("uid_hash", "STRING", "NULLABLE"),
    ("created_at", "TIMESTAMP", "REQUIRED"),
    ("input_types", "STRING", "REPEATED"),
    ("platform", "STRING", "NULLABLE"),
    ("content_language", "STRING", "NULLABLE"),
    ("n_claims", "INT64", "NULLABLE"),
    ("cache_tier_hit", "STRING", "NULLABLE"),
    ("labels", "STRING", "REPEATED"),
    ("panel_outcome", "STRING", "NULLABLE"),
    ("degraded", "BOOL", "NULLABLE"),
    ("total_latency_ms", "INT64", "NULLABLE"),
    ("stage_latency_ms", "JSON", "NULLABLE"),
    ("total_cost_usd", "FLOAT64", "NULLABLE"),
    ("model_cost_usd", "FLOAT64", "NULLABLE"),
    ("grounding_queries", "INT64", "NULLABLE"),
    ("vision_calls", "INT64", "NULLABLE"),
    ("tts_chars", "INT64", "NULLABLE"),
    ("error_code", "STRING", "NULLABLE"),
]

MODEL_CALLS = [
    ("check_id", "STRING", "NULLABLE"),
    ("stage", "STRING", "REQUIRED"),
    ("model_id", "STRING", "REQUIRED"),
    ("prompt_version", "STRING", "NULLABLE"),
    ("input_tokens", "INT64", "NULLABLE"),
    ("output_tokens", "INT64", "NULLABLE"),
    ("thinking_tokens", "INT64", "NULLABLE"),
    ("latency_ms", "INT64", "NULLABLE"),
    ("cost_usd", "FLOAT64", "NULLABLE"),
    ("success", "BOOL", "NULLABLE"),
    ("retry", "BOOL", "NULLABLE"),
]

EVAL_RUNS = [
    ("run_id", "STRING", "REQUIRED"),
    ("run_at", "TIMESTAMP", "REQUIRED"),
    ("model_config", "JSON", "NULLABLE"),
    ("prompt_versions", "JSON", "NULLABLE"),
    ("recall_at_5", "JSON", "NULLABLE"),
    ("verdict_agreement", "FLOAT64", "NULLABLE"),
    ("abstain_rate", "FLOAT64", "NULLABLE"),
    ("accuracy_when_answered", "FLOAT64", "NULLABLE"),
    ("p50_latency_ms", "INT64", "NULLABLE"),
    ("p95_latency_ms", "INT64", "NULLABLE"),
    ("cost_per_check", "FLOAT64", "NULLABLE"),
    ("baseline_run_id", "STRING", "NULLABLE"),
    ("drift_flag", "BOOL", "NULLABLE"),
]

TABLES = {"check_runs": CHECK_RUNS, "model_calls": MODEL_CALLS, "eval_runs": EVAL_RUNS}


def ensure_tables() -> None:
    s = get_settings()
    if not s.bigquery_enabled:
        return
    from google.cloud import bigquery

    client = bigquery.Client(project=s.gcp_project)
    for name, fields in TABLES.items():
        table = bigquery.Table(
            f"{s.gcp_project}.{s.bigquery_dataset}.{name}",
            schema=[bigquery.SchemaField(n, t, mode=m) for n, t, m in fields],
        )
        if name in ("check_runs", "model_calls"):
            table.time_partitioning = bigquery.TimePartitioning(field="created_at" if name == "check_runs"
                                                                else None)
        try:
            client.create_table(table, exists_ok=True)
        except Exception as e:  # noqa: BLE001
            log.warning("could not ensure table %s: %s", name, e)
