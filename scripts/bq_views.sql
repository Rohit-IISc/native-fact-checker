-- Dashboard views on BigQuery (docs/10 "Observability"). Created by scripts/create_bq_views.sh;
-- PROJECT and DATASET are replaced there. Looker Studio reads these for the deck's benchmark slide.

-- One row per check with its lane: T1 (exact or near-duplicate media/text), T2 (semantic), FULL, FAILED.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_checks` AS
SELECT
  check_id, created_at, DATE(created_at, 'Asia/Kolkata') AS day_ist, content_language, input_types,
  CASE WHEN error_code IN ('EXTRACTION_FAILED', 'INTERNAL') THEN 'FAILED'
       WHEN cache_tier_hit = 'T1' THEN 'T1' WHEN cache_tier_hit = 'T2' THEN 'T2' ELSE 'FULL' END AS lane,
  labels, n_claims, panel_outcome, degraded, error_code, total_latency_ms, total_cost_usd, model_cost_usd,
  grounding_queries, tts_chars,
  -- Rows before Oct 9 have no env: local runs used uid "dev-cli", deploy smoke checks "deploy-smoke".
  COALESCE(env, CASE uid_hash
    WHEN '118b5cb96a980a6dd1b60d3966170d0770b8b9d0b847f030abd4e6328c2eeaee' THEN 'dev'
    WHEN TO_HEX(SHA256('deploy-smoke')) THEN 'smoke' ELSE 'prod' END) AS env
FROM `PROJECT.DATASET.check_runs`
WHERE error_code IS NULL OR error_code != 'LINK_UNREADABLE';

-- Latency and cost by lane and day. Targets: T1 under 3 s, T2 under 6 s, FULL under 90 s (p95).
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_lanes_daily` AS
SELECT
  env, day_ist, lane, COUNT(*) AS checks,
  APPROX_QUANTILES(total_latency_ms, 100)[OFFSET(50)] AS p50_latency_ms,
  APPROX_QUANTILES(total_latency_ms, 100)[OFFSET(95)] AS p95_latency_ms,
  ROUND(AVG(total_cost_usd), 4) AS cost_per_check_usd,
  ROUND(SUM(total_cost_usd), 2) AS cost_usd
FROM `PROJECT.DATASET.v_checks`
GROUP BY env, day_ist, lane;

-- Filter env = 'prod' for real users; 'dev' is make try/accept, 'smoke' the deploy checks.
-- Headline numbers per day: volume, spend, cache hit rate, failures, degraded answers.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_daily` AS
SELECT
  env, day_ist, COUNT(*) AS checks,
  ROUND(SUM(total_cost_usd), 2) AS cost_usd,
  ROUND(AVG(total_cost_usd), 4) AS cost_per_check_usd,
  ROUND(100 * COUNTIF(lane IN ('T1', 'T2')) / COUNT(*), 1) AS cache_hit_pct,
  ROUND(100 * COUNTIF(lane = 'FAILED') / COUNT(*), 1) AS failed_pct,
  ROUND(100 * COUNTIF(degraded) / COUNT(*), 1) AS degraded_pct,
  APPROX_QUANTILES(IF(lane = 'FULL', total_latency_ms, NULL), 100 IGNORE NULLS)[OFFSET(95)] AS full_p95_latency_ms
FROM `PROJECT.DATASET.v_checks`
GROUP BY env, day_ist;

-- Verdict mix (one row per claim label) and languages.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_verdict_mix` AS
SELECT env, day_ist, content_language, lane, label, COUNT(*) AS claims
FROM `PROJECT.DATASET.v_checks`, UNNEST(labels) AS label
GROUP BY env, day_ist, content_language, lane, label;

-- Where the time goes in a full check: per stage, last 7 days.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_stage_latency_7d` AS
SELECT
  stage,
  COUNT(*) AS checks,
  APPROX_QUANTILES(ms, 100)[OFFSET(50)] AS p50_ms,
  APPROX_QUANTILES(ms, 100)[OFFSET(90)] AS p90_ms,
  APPROX_QUANTILES(ms, 100)[OFFSET(95)] AS p95_ms
FROM (
  SELECT * FROM (
    SELECT
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.fetching_link') AS INT64) AS fetching_link,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.extracting') AS INT64) AS extracting,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.tier2') AS INT64) AS tier2,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.searching') AS INT64) AS searching,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.packaging') AS INT64) AS packaging,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.judging') AS INT64) AS judging,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.composing') AS INT64) AS composing,
      SAFE_CAST(JSON_VALUE(stage_latency_ms, '$.speaking') AS INT64) AS speaking
    FROM `PROJECT.DATASET.check_runs`
    WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND stage_latency_ms IS NOT NULL
  )
  UNPIVOT (ms FOR stage IN (fetching_link, extracting, tier2, searching, packaging, judging, composing, speaking))
)
GROUP BY stage;

-- Model calls: cost, latency and failure rate per stage and model, per day.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_model_calls_daily` AS
SELECT
  DATE(_PARTITIONTIME) AS day_utc, stage, model_id, COUNT(*) AS calls,  -- ingestion-time partitions (UTC)
  ROUND(SUM(cost_usd), 4) AS cost_usd,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] AS p95_latency_ms,
  ROUND(100 * COUNTIF(NOT success) / COUNT(*), 1) AS failed_pct,
  SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens
FROM `PROJECT.DATASET.model_calls`
GROUP BY day_utc, stage, model_id;

-- Eval trend (scheduled runs every 3 days; baseline and drift flag included).
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_eval_trend` AS
SELECT
  run_at, run_id, label, dataset_version,
  SAFE_CAST(JSON_VALUE(recall_at_5, '$.overall') AS FLOAT64) AS recall_at_5,
  verdict_agreement, direction_agreement, abstain_rate, accuracy_when_answered,
  p50_latency_ms, p95_latency_ms, cost_per_check, total_cost_usd, n_gold, n_silver, drift_flag, baseline_run_id
FROM `PROJECT.DATASET.eval_runs`
WHERE label NOT IN ('smoke', 'experiment')
ORDER BY run_at;

-- Vertex pushback by hour (IST): 429s and 5xx per model and stage, including ones a retry recovered from.
-- Rows before Oct 9 have no created_at and are left out.
CREATE OR REPLACE VIEW `PROJECT.DATASET.v_rate_limits` AS
SELECT
  DATE(m.created_at, 'Asia/Kolkata') AS day_ist,
  EXTRACT(HOUR FROM m.created_at AT TIME ZONE 'Asia/Kolkata') AS hour_ist,
  COALESCE(c.env, 'unknown') AS env, m.model_id, m.stage,
  COUNT(*) AS calls,
  SUM(m.rate_limited) AS seen_429,
  COUNTIF(m.error_code = '429') AS failed_429,
  SUM(m.server_errors) AS seen_5xx,
  COUNTIF(m.error_code = 'TIMEOUT') AS timeouts
FROM `PROJECT.DATASET.model_calls` AS m
LEFT JOIN `PROJECT.DATASET.v_checks` AS c USING (check_id)
WHERE m.created_at IS NOT NULL
GROUP BY day_ist, hour_ist, env, model_id, stage;
