# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Sun Oct 4, 2026, evening
**Build-plan day:** Day 2 (media and links), started early. Day 0 and Day 1 done.
**Deployed:** https://ai-builder-2026.web.app (Hosting) -> Cloud Run `factcheck-api` revision 00002, asia-south1

## Done

- Day 0: GCP bootstrap, Firestore `(default)` + `dev-db` (IDs need 4+ chars, so not `dev`), rules on both,
  Cloud Run + Hosting deployed, Pub/Sub push wired.
- Day 1: text lane end to end (sign-in, consent, live progress, extractor, stub verdict, history).
- Dev loop: `make dev` (honcho), `make try`, `make accept`, `make record`, `make test` (replays fixtures).
- Answers in the content language (decision 15): `config/messages.yaml` (5 languages), result screen
  headings in the post's language, UI chrome in the display language.
- Extractor prompt 1.1: JOKE/SATIRE only for clear humour; fixed language codes (`en-IN` etc.).
- Day 2 media lane (`backend/app/intake/media.py`): magic-byte validation, GCS upload to
  `{project}-media/{check_id}/`, ffprobe duration (over 3 min: flagged `media_trimmed`, first 3 min
  checked), image pHash, video keyframe pHashes (1 every 5 s).
- Day 2 tier 1 media cache (`backend/app/cache/tier1.py`: `lookup_media`, `write_media`): exact sha256,
  near-duplicate image (Hamming <= 6), re-encoded video (60% of keyframes). Same photo + new caption hits.
- Day 2 link ladder (`backend/app/intake/links.py`: `fetch`): shorteners, YouTube (URL straight to
  Gemini), X oEmbed (marks `media_missing`), Meta oEmbed (needs token), generic page (Open Graph +
  trafilatura + og:image). SSRF guard at every hop, 5 MB cap, 10 s deadline. Unreadable link with no
  other content: "share a screenshot" prompt, quota refunded.
- Extractor is never called with empty input (Gemini invented a claim when it was).
- `extraction_base` timeout 15 s -> 25 s after measuring (text 4-6 s, images 7-10 s, rare stalls > 15 s).
- Fixed: `deploy_backend.sh` redeploys wiped the Pub/Sub push OIDC token (every push then 401).

## In progress

- Nothing mid-edit. Day 2 code is complete and deployed; Android share-target test is pending (below).

## Broken or risky

- Verdicts are still the Day 1 stub (always NOT_ENOUGH_EVIDENCE) until Day 3 (sub-agents) and Day 4 (panel).
  Because stub verdicts are never cached, repeat shares of checkable content are not cache hits yet;
  not-checkable results (greetings) are.
- Cloud Run caps request bodies at 32 MB, below our 50 MB share limit. Large videos need direct-to-GCS
  signed-URL upload. Most WhatsApp forwards are well under 32 MB.
- `meta-oembed-token` secret is empty: Instagram/Facebook links fall back to Open Graph (caption only).
- Extraction has no retry: one stalled Gemini call fails the check (refunded). Consider one retry.
- Not tested yet: Web Share Target from WhatsApp on a real Android phone (needs Rohit's phone).

## Next step

1. Rohit: install the PWA from https://ai-builder-2026.web.app on Android (Chrome menu -> Install app),
   then share a WhatsApp image, a video and a link to it. Report what happens.
2. Then start Day 3: `backend/app/agents/` web_search, factcheck_sites, source_credibility,
   media_provenance with timeouts; `scripts/seed_sources.py`; tier 2 cache.

## Latest `make accept` (Oct 4, real Gemini)

| case | result | label | lang | latency |
| --- | --- | --- | --- | --- |
| 05-ta-health-remedy | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | ta-IN | 4.9 s |
| 06-hi-free-recharge-scheme | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | hi-IN | 6.7 s |
| 06b-hi-laptop-scheme-image | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | hi-IN | 8.2 s |
| 07-id-vaccine-microchip | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | id-ID | 4.9 s |
| 08-en-chandrayaan3-landing | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | en-IN | 4.0 s |
| 11-hi-greeting | PASS | NOT_CHECKABLE | hi-IN | 2.3 s |
| 13-en-news-link | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | en-IN | 8.0 s |
| 15-kn-thin-local-claim | PASS | NOT_ENOUGH_EVIDENCE | kn-IN | 3.5 s |
| 90-en-prompt-injection | FAIL (stub verdict) | NOT_ENOUGH_EVIDENCE | en-IN | 4.1 s |

2/9 pass on label (expected while verdicts are stubbed); language 9/9; about $0.003 to $0.006 per case.
