# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Mon Oct 5, 2026, evening
**Build-plan day:** Day 1 of the calendar, but Days 0 to 4 are done (Day 5 composer done; TTS and card not yet).
**Deployed:** https://ai-builder-2026.web.app -> Cloud Run `factcheck-api` (asia-south1). `make smoke` verified it.

## Done

- Days 0-2: deploy, text/media/link lanes, tier 1 cache (exact + near-duplicate media), dev loop
  (`make dev`, `make try`, `make accept`, `make record`, `make test`, `make smoke`), answers in the
  content language.
- Day 3 fan-out (`backend/app/agents/`, run by `pipeline/investigate.py:fan_out`):
  - `web_search.py`: grounded Google Search (free text with [n] citations), then a classify call that cites
    sources by number. Every evidence URL is a page search returned; the model never types a URL.
  - `factcheck_sites.py`: Fact Check Tools API (original language, English, Hindi for other Indian
    languages; queries also without years), then Flash classifies.
  - `source_credibility.py`: offender record, RDAP domain age, lookalike domains, then Flash.
  - `media_provenance.py`: Cloud Vision web detection on images and 3 video keyframes, page publish dates.
  - Tool calls live in `agents/tools.py` (record/replay for tests).
- Day 3 tier 2 cache (`cache/tier2.py`): embeddings + Firestore vector search + Flash near-match.
  Paraphrases sit at 0.030-0.065 cosine distance but near-miss different claims at 0.013-0.052, so the
  near-match check decides (16/16 correct on test pairs incl. Rs 5 vs Rs 15). A repeat claim in other
  words, even another language: ~5-7 s and ~$0.001.
- Day 3 `scripts/seed_sources.py`: offender list from published fact checks (53 sources, 0 repeat
  offenders yet). Skips claimants that are the reviewing fact-checker (tempo.co, suara.com, tirto.id do this).
- Day 4 panel (`agents/packager.py`, `agents/panel_agents.py`, `pipeline/panel.py`): packager ->
  judge -> critic -> revision -> source policy. NOT_ENOUGH_EVIDENCE confidence capped at 50.
- Day 5 (part): composer writes native and English answers in parallel; checks the answer is in the
  expected script (en-IN answers came back in Hindi 1 in 3 before the fix); translate mode for cache reuse.
- Reliability: every stage has a deadline from the remaining 90 s budget and degrades instead of failing;
  hedged model calls for tail stalls; one retry on Vertex 5xx/429; stage errors recorded on the check doc
  (`stage_errors`, hidden from the API).
- Models (measured, see comments in `config/models.yaml`): flash = gemini-2.5-flash (3.8-flash took
  13-23 s per extraction), pro = gemini-2.5-pro with a 1024-token thinking budget (3.1-pro-preview 35-51 s).
- Meta oEmbed is tokenless since June 2026; Instagram/Facebook use oEmbed then Open Graph with an honest
  link-preview bot user agent (caption, @handle, date, photo).

## In progress

- Nothing mid-edit.

## Broken or risky

- **Decision for Rohit: source tiers.** VOA, PBS, TIME, Astronomy.com, The Tribune, Lead Stories (IFCN)
  are TIER_3 because they are not in `config/source_tiers.yaml`, so a TRUE claim covered only by such
  outlets ends NOT_ENOUGH_EVIDENCE (case 08 does this in about 1 of 3 runs). Adding outlets changes what
  can back a verdict, so it needs your sign-off.
- Not built with Google ADK: the fan-out uses asyncio over our instrumented model wrapper (cheaper, faster,
  testable). If ADK use matters for judging, wrap the agent functions in ADK agents.
- Cost ~$0.10 per full check, mostly grounding ($14 per 1000 queries after 5000 free per month; hedged
  searches duplicate queries). Cache hits ~$0.001.
- Latency 36-77 s per full check (target < 90 s); image checks are the slowest.
- Offender list is thin: the Fact Check API's claimant is usually a name, not a domain. A richer list needs
  appearance URLs from each fact check page's ClaimReview markup.
- Tier 1 cache hit for the same media with a caption in another language returns the original language
  (acceptance case 3 wants a new-language answer). Translate mode exists; wire it into the T1 path.
- Not built yet: TTS audio, correction card, FCM push, BigQuery dashboards, eval runner, Cloud Build trigger.
- Cloud Run caps uploads at 32 MB (our limit is 50 MB): large videos need signed-URL upload.

## Next step

1. Rohit: decide on the source-tier additions above; test the deployed app with WhatsApp shares on Android.
2. Day 5 rest: `backend/app/output/tts.py` (Gemini TTS), `output/card.py` (Pillow + libraqm + Noto),
   `output/notify.py` (FCM), then the public result page.

## Latest `make accept` (Oct 5, real models, after extractor 1.2)

| case | result | label (primary first) | lang | latency |
| --- | --- | --- | --- | --- |
| 05-ta-health-remedy | PASS | FALSE | ta-IN | 42.6 s |
| 06-hi-free-recharge-scheme | PASS | SCAM | hi-IN | 62.2 s |
| 06b-hi-laptop-scheme-image | PASS | SCAM | hi-IN | 77.6 s |
| 07-id-vaccine-microchip | PASS | FALSE | id-ID | 40.3 s |
| 08-en-chandrayaan3-landing | FAIL | NOT_ENOUGH_EVIDENCE (only TIER_3 sources found this run) | en-IN | 45.1 s |
| 11-hi-greeting | PASS | NOT_CHECKABLE | hi-IN | 1.5 s |
| 13-en-news-link | PASS | TRUE | en-IN | 59.6 s |
| 15-kn-thin-local-claim | PASS | NOT_ENOUGH_EVIDENCE | kn-IN | 50.1 s |
| 90-en-prompt-injection | PASS | FALSE | en-IN | 45.3 s |

8/9 pass; language 9/9; average 47 s; $0.95 for the suite. `make test`: 172 passed offline.
Latest `make smoke` (production): 5/5 full checks correct in 36-77 s, tier 2 repeat in 4.9 s.
