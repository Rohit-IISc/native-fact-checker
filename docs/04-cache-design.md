# 04. Cache design

The cache is shared by all users. Most forwards are repeats, so this is where most of the speed and cost saving comes from.

## Tier 1: exact and near-exact media (before extraction)

Keys written to `cache_keys/{key}` pointing to one or more `verdict_id`s:

| Key | Built from | Match rule |
| --- | --- | --- |
| `sha256:{hex}` | Raw bytes of each file | Exact |
| `phash:{hex}` | 64-bit pHash of each image | Hamming distance up to 6. Stored with 16-bit prefix buckets (`phash_prefix`) so lookup reads one small bucket, then compares in code |
| `vphash:{hex}` | pHash of video keyframes (every 5 s) | 60% or more of keyframes within distance 6 |
| `text:{hex}` | SHA-256 of normalized text (NFKC, lowercase, whitespace collapsed, emojis and "Forwarded" markers removed) | Exact |
| `url:{hex}` | SHA-256 of normalized URL | Exact |

Tier 1 hit returns in about 1 to 2 s. If the cached verdict is LIVE_EVENT and older than 7 days, still return it but also run the date-tag rule below.

## Tier 2: semantic claim match (after extraction)

- Embed `claim_en` with the embedding model at 768 dimensions (Firestore vector fields allow up to 2048)
- Firestore vector search on `claims` collection, `find_nearest` with COSINE, limit 5, filtered by `status == ACTIVE`
- Distance up to 0.10: candidate match. Distance 0.10 to 0.18: candidate, lower confidence. Over 0.18: no match. Tune on Day 3 with 50 paraphrase pairs
- Every candidate goes through the near-match check (Flash, `prompts/02_near_match.md`): same claim, same place, same time context? Returns SAME, SAME_CLAIM_DIFFERENT_DATE, DIFFERENT
  - SAME: reuse verdict
  - SAME_CLAIM_DIFFERENT_DATE: run the full pipeline but add the cached verdict as context evidence
  - DIFFERENT: full pipeline
- Tier 2 hit returns in about 5 s from share

## New language on a cached verdict

Verdicts store composed text per language: `answers.{lang}`. If the requesting content's language is missing, run the composer in translate mode (Flash) from the English answer, then TTS, then store it. About 8 to 10 s.

## Expiry and archive

| Time sensitivity | Rule |
| --- | --- |
| LIVE_EVENT (flood today, ongoing riot, election-day claim) | Active for 90 days, then moved to ARCHIVED |
| EVERGREEN (old war or riot photos reused, health myths, fake schemes, fake quotes) | Never expires |

ARCHIVED verdicts are never returned directly. They are added to the evidence pack as "previously checked on {date}: {label}" context, so the Judge still benefits.

## Date tag rule

Every claim stores `event_date` (when the event happened per evidence) and `claimed_date` (when the post says it happened). When a LIVE_EVENT claim matches, compare the new post's claimed date with the stored event date. If they differ (yesterday's flood shared today as "today"), the answer becomes MISLEADING with "this happened on {event_date}, not today", reusing the stored evidence. This is the near-match check's SAME_CLAIM_DIFFERENT_DATE path, decided by code when dates are explicit.

## Versioning

A verdict is never edited in place. A re-check writes a new verdict and sets `superseded_by` on the old one. Cache keys point to the newest verdict.

## What is not cached

Checks that ended NOT_CHECKABLE are cached by tier 1 keys only (cheap repeat answers for viral greetings). Checks that ended `failed` are not cached. NOT_ENOUGH_EVIDENCE verdicts are cached for 3 days only, because evidence often appears later.
