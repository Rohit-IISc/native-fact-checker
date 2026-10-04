# 06. API contract (v1)

Base: `https://{cloud-run-url}/v1`. Firebase Hosting rewrites `/api/**` to the Cloud Run service so the PWA calls same-origin `/api/v1/...`.

All endpoints except results and health need headers `Authorization: Bearer {Firebase ID token}` and `X-Firebase-AppCheck: {token}`.

## POST /v1/checks

Multipart form: `text` (optional), `url` (optional), `files[]` (optional, up to 10 images or 1 video or 1 audio), `client_lang` (UI language).

Responses:
- `200` cache hit: `{ check_id, status: "DONE", cache_tier_hit: "T1", result: CheckResult }`
- `202` accepted: `{ check_id, status: "RUNNING" }`. Client then listens to `checks/{check_id}` in Firestore
- `400` invalid input with `error_code` (TOO_LARGE, TOO_MANY_FILES, UNSUPPORTED_TYPE, VIDEO_TOO_LONG, EMPTY)
- `401` / `403` auth or App Check failure
- `429` `{ error_code: "DAILY_LIMIT", resets_at }`

## GET /v1/checks/{check_id}

Owner only. Same `CheckResult` shape as the Firestore doc, for clients that cannot listen to Firestore.

## GET /v1/me/history?cursor=

Owner's past checks, 20 per page.

## GET /v1/me/quota

`{ used, limit, resets_at }`

## POST /v1/me/fcm-token

`{ token }` registers a push token.

## POST /v1/me/consent

Records first-use consent (doc 08).

## GET /v1/results/{verdict_id}?lang=

Public, no auth, rate limited per IP. Returns only public fields: claim, label, confidence, what is true, sources, audio_url, card_url for the language. Powers the shareable result page.

## POST /v1/checks/{check_id}/feedback

`{ helpful: bool, reason? }`. Stored for evaluation.

## POST /internal/pipeline

Pub/Sub push only. Verified by OIDC token from the push subscription's service account. Body: Pub/Sub envelope with `{ check_id }`. Idempotent: if the check is already DONE, ack and return.

## GET /healthz

## CheckResult shape

See `schemas/models.py` (`CheckResult`, `ClaimResult`, `Evidence`, `AnswerText`).

## B2B API (documented, not built)

Same pipeline behind `/v1/b2b/checks` with API keys (stored hashed in Firestore, issued manually), per-key quotas, webhook callback instead of Firestore listeners, and no audio by default. Nothing in the pipeline depends on the web client, so this is an additive change.
