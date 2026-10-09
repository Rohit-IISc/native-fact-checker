#!/usr/bin/env bash
# Log-based metrics and alert policies (docs/10 "Observability"). Re-runnable: updates what exists.
#   - check error rate over 5% in 15 minutes          (factcheck-api "check failed" vs "check_run" logs)
#   - p95 full-check latency over 120 s in 30 minutes  (check_run.total_latency_ms, cache misses only)
#   - model spend over ALERT_DAILY_USD in a day         (check_run.total_cost_usd; our own measured cost)
#   - eval drift                                        (eval-runner logs "eval drift" at ERROR)
#   - eval job failed                                   (eval-runner task ends with an error)
# Alerts go to ALERT_EMAIL (not stored in the repo). Only production traffic counts: Cloud Run service
# factcheck-api, so local runs and the eval job's own pipeline runs never trigger the check alerts.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
: "${ALERT_EMAIL:?Set ALERT_EMAIL (who gets the alerts)}"
DAILY_USD="${ALERT_DAILY_USD:-30}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SERVICE='resource.type="cloud_run_revision" AND resource.labels.service_name="factcheck-api"'

metric() {  # name, description, filter, [value field for a distribution]
  local name="$1" desc="$2" filter="$3" field="${4:-}"
  if [ -n "$field" ]; then
    cat >"$TMP/$name.yaml" <<EOF
description: "$desc"
filter: '$filter'
valueExtractor: EXTRACT(jsonPayload.$field)
metricDescriptor: {metricKind: DELTA, valueType: DISTRIBUTION, unit: "1"}
bucketOptions: {exponentialBuckets: {numFiniteBuckets: 64, growthFactor: 1.25, scale: 0.01}}
EOF
  else
    cat >"$TMP/$name.yaml" <<EOF
description: "$desc"
filter: '$filter'
metricDescriptor: {metricKind: DELTA, valueType: INT64, unit: "1"}
EOF
  fi
  if gcloud logging metrics describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud logging metrics update "$name" --project="$PROJECT_ID" --config-from-file="$TMP/$name.yaml" >/dev/null
  else
    gcloud logging metrics create "$name" --project="$PROJECT_ID" --config-from-file="$TMP/$name.yaml" >/dev/null
  fi
  echo "metric $name"
}

metric check_run "Finished checks (any outcome)" "$SERVICE AND jsonPayload.message=\"check_run\""
metric check_failed "Checks that failed" "$SERVICE AND jsonPayload.message=\"check failed\""
metric full_check_latency_ms "Latency of checks that ran the full pipeline" \
  "$SERVICE AND jsonPayload.message=\"check_run\" AND jsonPayload.cache_tier_hit=\"NONE\"" total_latency_ms
metric check_cost_usd "Measured cost per check (models, grounding, vision, TTS)" \
  "$SERVICE AND jsonPayload.message=\"check_run\"" total_cost_usd

# Email channel (one per address).
CHANNEL="$(gcloud alpha monitoring channels list --project="$PROJECT_ID" \
  --filter="type=\"email\" AND labels.email_address=\"$ALERT_EMAIL\"" --format='value(name)' | head -1)"
if [ -z "$CHANNEL" ]; then
  CHANNEL="$(gcloud alpha monitoring channels create --project="$PROJECT_ID" --type=email \
    --display-name="Fact checker alerts" --channel-labels="email_address=$ALERT_EMAIL" --format='value(name)')"
fi
echo "channel $CHANNEL"

policy() {  # display name, file
  local existing
  existing="$(gcloud alpha monitoring policies list --project="$PROJECT_ID" \
    --filter="displayName=\"$1\"" --format='value(name)' | head -1)"
  if [ -n "$existing" ]; then
    gcloud alpha monitoring policies update "$existing" --project="$PROJECT_ID" --policy-from-file="$2" >/dev/null
  else
    gcloud alpha monitoring policies create --project="$PROJECT_ID" --policy-from-file="$2" >/dev/null
  fi
  echo "policy $1"
}

U='logging_googleapis_com:user_'
promql() {  # display name, PromQL, duration, documentation
  cat >"$TMP/p.json" <<EOF
{
  "displayName": "$1",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "documentation": {"content": "$4", "mimeType": "text/markdown"},
  "alertStrategy": {"autoClose": "86400s"},
  "conditions": [{
    "displayName": "$1",
    "conditionPrometheusQueryLanguage": {"query": "$2", "duration": "$3", "evaluationInterval": "60s"}
  }]
}
EOF
  policy "$1" "$TMP/p.json"
}

promql "Check error rate over 5%" \
  "sum(rate(${U}check_failed{monitored_resource=\\\"cloud_run_revision\\\"}[15m])) / sum(rate(${U}check_run{monitored_resource=\\\"cloud_run_revision\\\"}[15m])) > 0.05" \
  "0s" "More than 5% of checks failed in the last 15 minutes. Look at Cloud Logging: jsonPayload.message=\\\"check failed\\\" (error_code says which stage)."
promql "Full check p95 latency over 120 s" \
  "histogram_quantile(0.95, sum by (le) (rate(${U}full_check_latency_ms_bucket{monitored_resource=\\\"cloud_run_revision\\\"}[30m]))) > 120000" \
  "0s" "p95 latency of full checks is over 120 s (target 90 s). BigQuery view factcheck.v_stage_latency_7d shows which stage; 429s from Vertex show as retries in the logs."
promql "Model spend over ${DAILY_USD} USD a day" \
  "sum(increase(${U}check_cost_usd_sum{monitored_resource=\\\"cloud_run_revision\\\"}[1d])) > ${DAILY_USD}" \
  "0s" "Measured model, grounding, vision and TTS cost of production checks in the last 24 hours is over ${DAILY_USD} USD. See factcheck.v_daily. The hard stop is the global daily cap on new checks (config/limits.yaml)."

# Log-match policies: eval drift and eval job failure.
logmatch() {  # display name, filter, documentation
  cat >"$TMP/l.json" <<EOF
{
  "displayName": "$1",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "documentation": {"content": "$3", "mimeType": "text/markdown"},
  "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "604800s"},
  "conditions": [{"displayName": "$1", "conditionMatchedLog": {"filter": "$2"}}]
}
EOF
  policy "$1" "$TMP/l.json"
}

JOB='resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"eval-runner\"'
logmatch "Eval drift" "$JOB AND severity>=ERROR AND (jsonPayload.message:\\\"eval drift\\\" OR textPayload:\\\"eval drift\\\")" \
  "The scheduled eval dropped more than 5 points (recall at 5 or verdict agreement) or p95 latency rose over 30% against the baseline. Details: factcheck.v_eval_trend and the run's details_uri. Firestore config/flags.model_review_needed is set."
logmatch "Eval job failed" "$JOB AND severity>=ERROR AND textPayload:\\\"Traceback\\\"" \
  "The eval-runner job crashed. Check its execution logs."
echo "Alerts ready (emails to the address in ALERT_EMAIL)."
