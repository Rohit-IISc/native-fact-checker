# 05. Data model

## Firestore (Native mode, asia-south1, databases `(default)` for prod and `dev` for local)

| Collection | Doc id | Key fields | Who reads |
| --- | --- | --- | --- |
| `users` | uid | display_name, email, created_at, ui_language, fcm_tokens[], consent_at, role (USER, JUDGE, ADMIN) | Owner |
| `usage` | `{uid}_{YYYYMMDD}` (IST date) | count, updated_at | Server only |
| `checks` | check_id (ULID) | uid, created_at, input_types[], source_url, platform, stage, stage_label_key, progress, content_language, claim_ids[], verdict_ids[], status (RUNNING, DONE, FAILED, LIMIT), cache_tier_hit (NONE, T1, T2), degraded, error_code, latency_ms | Owner |
| `verdicts` | verdict_id (ULID) | claim_original, claim_en, claim_type, label, confidence, band, panel_outcome, what_is_true_en, evidence[] (embedded, max 12), evidence_for_ids[], evidence_against_ids[], ai_generation, event_date, claimed_date, time_sensitivity, status (ACTIVE, ARCHIVED, SUPERSEDED), superseded_by, answers.{lang} {headline, summary, body, audio_script, audio_url, card_url}, created_at, expires_at, model_versions, prompt_versions | Public read of whitelisted fields for result page |
| `claims` | claim_id | verdict_id, claim_en, embedding (vector 768), status, time_sensitivity, created_at | Server only |
| `cache_keys` | key string | type, verdict_ids[], phash_prefix (for buckets), created_at | Server only |
| `sources` | normalized domain or `platform:handle` | tier, category, false_count, misleading_count, true_count, last_flagged_at, origin (SEED_TIERS, CLAIMREVIEW_HARVEST, OWN_VERDICTS), domain_created_at | Server only |
| `config` | `models`, `limits`, `flags` | Runtime overrides of config/*.yaml (lets eval switch a model without a deploy) | Server only |
| `users/{uid}/history` | check_id | created_at, headline in content language, label, thumbnail_hash | Owner |

Indexes: vector index on `claims.embedding` (768, COSINE) with `status` as a pre-filter field; composite on `checks(uid, created_at desc)`; `cache_keys(phash_prefix)`.

Security rules: clients can read `checks` where `uid == request.auth.uid`, their own `users` doc and `history`. All writes go through the backend (Admin SDK). The public result page reads via `GET /v1/results/{verdict_id}` so rules never expose `verdicts` directly.

## Cloud Storage

| Bucket | Content | Lifecycle |
| --- | --- | --- |
| `{project}-media` | Raw uploads and fetched media | Delete after 1 day |
| `{project}-outputs` | Audio MP3 and card PNG per verdict and language | Keep |
| `{project}-eval` | Eval datasets and run artifacts | Keep |

Outputs are served through signed URLs (7 days) or a public read on the outputs bucket only. Prefer signed URLs.

## BigQuery dataset `factcheck` (asia-south1)

`check_runs` (one row per check): check_id, uid_hash (SHA-256 of uid, never raw uid), created_at, input_types, platform, content_language, n_claims, cache_tier_hit, labels, panel_outcome, degraded, total_latency_ms, stage_latency_ms (JSON), total_cost_usd, model_cost_usd, grounding_queries, vision_calls, tts_chars, error_code.

`model_calls` (one row per model call): check_id, stage, model_id, prompt_version, input_tokens, output_tokens, thinking_tokens, latency_ms, cost_usd, success, retry.

`eval_runs`: run_id, run_at, model_config (JSON), prompt_versions (JSON), recall_at_5 per language pair, verdict_agreement, abstain_rate, accuracy_when_answered, p50 and p95 latency, cost_per_check, baseline_run_id, drift_flag.

Write with the BigQuery Storage Write API (or `insert_rows_json` for the prototype) at the end of each check. Never block the user response on this write.
