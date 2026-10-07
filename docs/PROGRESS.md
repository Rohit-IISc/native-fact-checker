# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Wed Oct 7, 2026, late evening
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

- Acceptance (Oct 7 evening, 19 cases, Rohit's notes): 11/19 pass, language 19/19. Open items:
  - 01 Kannada flood video ends NOT_ENOUGH_EVIDENCE (real Bengaluru rain news on 6 Oct 2026 and no
    source for the 2022 origin found); 02 and 03 inherit it from the cache (both cache paths work:
    02 is a T1 keyframe-pHash hit, 03 answers in Hindi in 4.4 s).
  - 12 NBT Holi satire: FALSE, Rohit expects MISLEADING. The claim is extracted as the event, for which
    FALSE is literal; the extractor should frame a newspaper photo as media ("this page reports...").
  - 10b: judge gave AI signals but none for a real photo; the case wants signals both ways.
  - 13 BBC link and 08 Chandrayaan: search variance (TIER_3-only coverage some runs).
  - Latency: 06b and 90 at 97-100 s with 3 checks running at once (Vertex tail latency).
- Instagram: links work (caption, @handle, date, photo via Open Graph). Reels: Instagram gives no video to
  link previews, so only caption + thumbnail are checked and the user is asked for a screen recording.
- X link case: open until Rohit sends a live post URL (case 14 is a screenshot).
- Not built yet: correction card, FCM push, BigQuery dashboards, eval runner, Cloud Build trigger.

## Next step

1. Extractor: frame newspaper or screenshot pages as media claims; judge: always fill both AI-signal sides.
2. Find the 2022 origin of the flood video (case 01): keyframe search via Vision on full-resolution frames.
3. Day 5 rest: correction card, FCM push.
