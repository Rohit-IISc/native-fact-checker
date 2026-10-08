# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Thu Oct 8, 2026, morning
**Build-plan day:** Day 3 of the calendar; Days 0 to 4 done, Day 5 started (audio done).
**Deployed:** https://ai-builder-2026.web.app -> Cloud Run `factcheck-api` (asia-south1), commit 2d0803c+.
**Audio samples for native speakers:** https://claude.ai/artifact/3uKEHUsp5hdXoVFo87SJeo (private; share it).

## Done

- Days 0-3 (see git history): deploy, text/media/link lanes, tier 1 + tier 2 caches, four evidence agents,
  offender list, dev loop (`make dev/try/accept/record/test/smoke`).
- Day 4 panel plus the Oct 7 finish:
  - `config/source_tiers.yaml`: tier 1 fact-checkers = IFCN "Active" signatories on 2026-10-07, domains
    from the publishers' own ClaimReview URLs. Alt News (verified 2019) and Tempo Cek Fakta (2022) are
    not on the Active tab: moved to tier 2. VOA, PBS, TIME, The Tribune added as tier 2 (Rohit).
  - Judge/critic 1.1: real media with a wrong date or place is MISLEADING, never FALSE (3/3 on a test pack).
  - `pipeline/panel.py:reconcile_stances`: for/against lists follow each item's classified stance; an item
    whose stance points the other way cannot back a decisive label.
  - Split verdicts: composer writes both readings in the post's language; result and public pages show them.
  - AI images: extractor 1.6 (512-token thinking budget, `flash_think`) makes claims about the post's own
    media; claim type reaches the judge; `ai_generation` survives revisions.
  - Every prompt gets today's date (shared rules 1.1): models had called real 2026 fact checks
    "impossible future dates".
- Day 5 audio (`backend/app/output/tts.py`): Gemini TTS, voice per language, MP3 via ffmpeg, stored in the
  outputs bucket, served by `GET /v1/results/{id}/audio`. Generated after DONE (TTS takes 18-24 s);
  the UI shows "audio is being prepared" until the player appears. Verified by round-trip transcription
  in all 5 languages and in production through Hosting.

## In progress

- Nothing mid-edit.

## Broken or risky

Pass rates (Oct 8, real models; `make accept REPEAT=2`, plus later single runs):
- Stable (passed every run): 05, 06, 06b, 07, 08, 10a, 10b, 11, 14, 15, 16 (X quote tweet), 90; 01b 2/2 after fixes.
- Flaky: 04 (1/2 then pass), 09 (1/2 then pass).
- 01 Kannada flood video (and 02/03, which reuse its verdict from cache; both cache paths work):
  2/2 MISLEADING, then 0/2 NOT_ENOUGH_EVIDENCE. Search finds The Quint's fact check of this video
  but it is sometimes classified CONTEXT, and real Bengaluru rain news this week makes "flooding today"
  look half-true. Cautious, not wrong; high variance.
- 12 NBT Holi satire: FALSE or NOT_ENOUGH_EVIDENCE, Rohit expects MISLEADING. Needs Rohit's decision on
  letting neutral media observations (satire tag, masthead date) into the evidence pack.
- 13 BBC link: NOT_ENOUGH_EVIDENCE when search returns only TIER_3 coverage of a true event.
- Vertex 429 RESOURCE_EXHAUSTED under load (3 checks in parallel). Now retried with backoff (seen
  recovering); Gemini 2.5 on Vertex uses dynamic shared quota, so heavy judging-week load may still hit
  it. Option: Provisioned Throughput (costs money; Rohit to decide).
- Instagram reels: only caption + thumbnail (Instagram gives no video to link previews).
- Not built yet: correction card, FCM push, BigQuery dashboards, eval runner, Cloud Build trigger.

## Next step

1. Rohit: decide on media observations in the evidence pack (case 12); decide on Provisioned Throughput.
2. Stance classification for "this exact video is old" fact checks (case 01).
3. Day 5 rest: correction card, FCM push.

