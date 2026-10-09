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
    ("env", "STRING", "NULLABLE"),  # Oct 9: prod (Cloud Run), smoke (deploy checks) or dev (make try/accept)
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
    # Added Oct 9: per-call time and Vertex pushback (429 clustering by hour; scripts/bq_views.sql v_rate_limits)
    ("created_at", "TIMESTAMP", "NULLABLE"),
    ("error_code", "STRING", "NULLABLE"),
    ("rate_limited", "INT64", "NULLABLE"),
    ("server_errors", "INT64", "NULLABLE"),
    ("fallback", "BOOL", "NULLABLE"),
    ("priority", "BOOL", "NULLABLE"),
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
    # Added Oct 9 (eval runner): ensure_eval_table() adds them to an existing table.
    ("direction_agreement", "FLOAT64", "NULLABLE"),
    ("total_cost_usd", "FLOAT64", "NULLABLE"),
    ("n_recall", "INT64", "NULLABLE"),
    ("n_gold", "INT64", "NULLABLE"),
    ("n_silver", "INT64", "NULLABLE"),
    ("dataset_version", "STRING", "NULLABLE"),
    ("label", "STRING", "NULLABLE"),
    ("details_uri", "STRING", "NULLABLE"),
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
            _add_missing_columns(client, client.create_table(table, exists_ok=True), table.schema)
        except Exception as e:  # noqa: BLE001
            log.warning("could not ensure table %s: %s", name, e)


def _add_missing_columns(client, table, schema) -> None:
    """BigQuery allows appending NULLABLE columns; new fields in the lists above reach existing tables."""
    have = {f.name for f in table.schema}
    missing = [f for f in schema if f.name not in have]
    if missing:
        table.schema = [*table.schema, *missing]
        client.update_table(table, ["schema"])


def ensure_eval_table() -> None:
    """eval_runs with every column in EVAL_RUNS: creates it, or appends columns added since (the eval runner
    writes even when BIGQUERY_ENABLED is off for its pipeline runs)."""
    from google.cloud import bigquery

    s = get_settings()
    client = bigquery.Client(project=s.gcp_project)
    ref = f"{s.gcp_project}.{s.bigquery_dataset}.eval_runs"
    schema = [bigquery.SchemaField(n, t, mode=m) for n, t, m in EVAL_RUNS]
    _add_missing_columns(client, client.create_table(bigquery.Table(ref, schema=schema), exists_ok=True), schema)
