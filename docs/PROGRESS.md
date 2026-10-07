# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Wed Oct 7, 2026, evening
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

- **Waiting on Rohit's notes**: the 9 sample cases (`tests/acceptance/01*`, `04`, `09`, `10a`, `10b`, `12`,
  `14`) use gold fact-check URLs and captions I proposed (marked PROPOSED in each file) because the notes
  did not arrive.
- **Alt News and Tempo**: possibly on the IFCN "In Renewal" tab, which could not be read automatically.
  If they are, move them back to tier 1.
- Run-to-run variance: retrieval decides several cases (01, 04, 13 flip between pass and
  NOT_ENOUGH_EVIDENCE). Case 04: Vision cannot match a 360x270 screenshot crop of a famous AFP photo;
  next idea is a scene-description search query from the extractor.
- Vertex returned 429 (resource exhausted) once during heavy testing; check quotas before judging week.
- Latency 45-85 s per full check; extraction now 10-13 s for images (thinking budget). Audio +18-24 s
  after the answer.
- Not built yet: correction card, FCM push, T1 cache answer in a new caption language, BigQuery dashboards,
  eval runner, Cloud Build trigger. Cloud Run caps uploads at 32 MB.

## Next step

1. Rohit: share the audio page with native speakers; send the notes with the intended fact-check URLs;
   check whether Alt News and Tempo are on the IFCN "In Renewal" tab.
2. Day 5 rest: `output/card.py` (Pillow + libraqm + Noto correction card), `output/notify.py` (FCM push),
   tier 1 hit with a caption in a new language -> translate + speak.

## Latest `make record` (Oct 7, all prompts current; samples/ cases run but never recorded)

| case | result | label (primary first) | lang | cache | gold | latency |
| --- | --- | --- | --- | --- | --- | --- |
| 01-hi-delhi-flood-screenshot | FAIL | NOT_ENOUGH_EVIDENCE | hi-IN | NONE | site | 51.5 s |
| 01a-hi-delhi-flood-video | PASS | MISLEADING | hi-IN | NONE | no | 62.1 s |
| 01b-hi-delhi-flood-video-reshare | PASS | MISLEADING | hi-IN | T1 | - | 0.0 s |
| 04-hi-delhi-police-photo | FAIL | NOT_ENOUGH_EVIDENCE | hi-IN | NONE | no | 54.5 s |
| 05-ta-health-remedy | PASS | FALSE | ta-IN | NONE | - | 41.4 s |
| 06-hi-free-recharge-scheme | PASS | SCAM | hi-IN | NONE | - | 47.9 s |
| 06b-hi-laptop-scheme-image | PASS | SCAM | hi-IN | NONE | - | 77.8 s |
| 07-id-vaccine-microchip | PASS | FALSE | id-ID | NONE | - | 49.1 s |
| 08-en-chandrayaan3-landing | PASS | TRUE | en-IN | NONE | - | 50.6 s |
| 09-hi-amit-shah-fake-quote | PASS | FALSE | hi-IN | NONE | page | 67.6 s |
| 10a-en-mumbai-flyover-bus-ai | PASS | FALSE | en-IN | NONE | page | 48.4 s |
| 10b-en-modi-shah-old-photo-ai | PASS | FALSE | en-IN | NONE | page | 46.2 s |
| 11-hi-greeting | PASS | NOT_CHECKABLE | hi-IN | NONE | - | 4.3 s |
| 12-hi-nbt-holi-satire | PASS | FALSE | hi-IN | NONE | no | 73.8 s |
| 13-en-news-link | PASS | TRUE | en-IN | NONE | - | 81.8 s |
| 14-en-putin-cnn-fake | PASS | FALSE | en-IN | NONE | page | 81.7 s |
| 15-kn-thin-local-claim | PASS | NOT_ENOUGH_EVIDENCE | kn-IN | NONE | - | 48.7 s |
| 90-en-prompt-injection | PASS | FALSE | en-IN | NONE | - | 52.0 s |

16/18 pass; language 18/18; average 52 s; $1.90 for the suite. `make test`: 205 passed offline.
Latest `make smoke` (production, with audio): 6/6 correct, all six spoken answers served (HTTP 200).
