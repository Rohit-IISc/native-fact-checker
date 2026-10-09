# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Fri Oct 9, 2026
**Build-plan day:** Day 6 work on Fri Oct 9: Days 0 to 5 done; Day 6 (measure) deployed; pushes to main deploy via Cloud Build.
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
- Media observations (decision 40): extractor 1.11 lists `media_markers` (satire tags, masthead dates,
  watermarks); `agents/packager.py:media_evidence` adds one `media_itself` item per claim (NOT_A_SOURCE,
  CONTEXT); `verify/source_policy.py` ignores them when counting sources. Judge 1.4, critic 1.3.
- Day 5 correction card (`backend/app/output/card.py`): 1080 x 1350 PNG drawn with Pillow + libraqm and
  Noto fonts; verdict colour band, label in the answer language, claim, what is true, top 2 sources, link.
  Drawn on first request by `GET /v1/results/{id}/card?lang=` and kept in the outputs bucket, so cache
  hits and new languages get one too. "Share card to WhatsApp" button (Web Share API with the PNG).
  Card strings per language in `config/languages.yaml`. Checked visually in all 5 languages.
- Day 5 push (`backend/app/output/notify.py`): FCM data message on DONE, "Result ready: {label}" in the UI
  language, headline as body; dead tokens removed; never fails a check. The PWA asks for permission once a
  check starts (`frontend/src/lib/push.ts`); the service worker skips it when the result is on screen.
  Needs a phone test (eval/TESTS-TO-DO.md).
- Day 6 measure (Oct 9):
  - Eval (`eval/runner.py`, `eval/datasets.py`): recall at 5 (claim restated in another language, fact-check
    retrieval only) and verdict regression (gold from ClaimReview ratings, silver from our AGREED/HIGH
    verdicts) on an overlay store (production cache untouched). Row in BigQuery `eval_runs`, details in
    `gs://ai-builder-2026-eval/runs/`, drift vs baseline sets Firestore `config/flags.model_review_needed`.
    Dataset v2 frozen in the eval bucket. Cloud Run Job `eval-runner`, Scheduler every 3 days 03:00 IST.
  - BigQuery views `factcheck.v_*` (`scripts/bq_views.sql`): lanes, daily, verdict mix, stage latency,
    model calls, eval trend. New `env` column (prod/dev/smoke) keeps test traffic out; tier 1 hits now
    write check_runs too (they were missing).
  - Alerts (`scripts/create_alerts.sh`): error rate, full-check p95, daily model spend (30 USD), eval drift,
    eval job failure; email to Rohit.
  - Cloud Build: `cloudbuild.yaml` (gitleaks, ruff, pytest, deploy), `scripts/setup_cloud_build.sh`
    (build-sa, PWA keys in Secret Manager, GitHub connection, trigger). Trigger `deploy-on-push` deploys
    every push to `main` (working branch merged into main on Oct 9).
  - `make deploy-ops` re-runs eval deploy, views and alerts.
- `eval/TESTS-TO-DO.md`: every test still to do (phone, verdict quality, native speakers, load, unbuilt).
- Day 5 audio (`backend/app/output/tts.py`): Gemini TTS, voice per language, MP3 via ffmpeg, stored in the
  outputs bucket, served by `GET /v1/results/{id}/audio`. Generated after DONE (TTS takes 18-24 s);
  the UI shows "audio is being prepared" until the player appears. Verified by round-trip transcription
  in all 5 languages and in production through Hosting.

## In progress

- Nothing mid-edit.

## Broken or risky

Latest `make accept` (Oct 9 afternoon, after the case 01 and wording fixes): 14/20, avg 60.7 s, $2.04, on a
slow Vertex day (extractor p95 27 s vs 18-21 s before; web search 6% failures). Targeted REPEAT=2: 01 2/2
MISLEADING (the answer is now about the sharer's own claim), 12 1/2 (the miss ran over budget), 01b 0/2
(web search timed out; the Fact Check Tools API has no match for it, so it depends on web search).
Wording: 0 of 6 MISLEADING answers call the post false (composer 1.3 gets the verdict word).
Earlier Oct 9 (cross-language search fix, record jobs=2): 18/20, avg 44.8 s; failing 10a and 13.

Previous `make record` (Oct 8 evening, jobs=3): 15/20, avg 55.4 s, $2.07. Failing: 01b, 13 (known), and 09,
10a, 10b, which hit agent timeouts and a 429 under 3 parallel cases; re-run one at a time, all three passed
(46-57 s), and so did 06 (whose composer had timed out). Load, not the change: see decision 41.

Earlier pass rates (Oct 8, real models; `make accept REPEAT=2`, plus later single runs):
- Stable (passed every run): 05, 06, 06b, 07, 08, 10a, 10b, 11, 14, 15, 16 (X quote tweet), 90; 01b 2/2 after fixes.
- Flaky: 04 (1/2 then pass), 09 (1/2 then pass).
- 01 Kannada flood video (and 02/03, which reuse its verdict from cache; both cache paths work):
  2/2 MISLEADING, then 0/2 NOT_ENOUGH_EVIDENCE. Search finds The Quint's fact check of this video
  but it is sometimes classified CONTEXT, and real Bengaluru rain news this week makes "flooding today"
  look half-true. Cautious, not wrong; high variance.
- 12 NBT Holi satire: now MISLEADING 3/3 (was FALSE or NOT_ENOUGH_EVIDENCE), always backed by external
  sources (BOOM, or UN, Al Jazeera and India Today). One run's English summary said "false" under the
  MISLEADING label: composer wording to tighten.
- 13 BBC link: NOT_ENOUGH_EVIDENCE when search returns only TIER_3 coverage of a true event.
- Vertex 429 RESOURCE_EXHAUSTED under load (3 checks in parallel). Now retried with backoff (seen
  recovering); Gemini 2.5 on Vertex uses dynamic shared quota, so heavy judging-week load may still hit
  it. Provisioned Throughput: not now (decision 41); see "Before the final presentation".
- Instagram reels: only caption + thumbnail (Instagram gives no video to link previews).
- Not built yet: signed-URL upload (Cloud Run caps uploads at 32 MB; we promise 50 MB). Looker Studio
  dashboard and the billing budget need Rohit (eval/TESTS-TO-DO.md section 5).

Eval baseline (Oct 9, dataset v2): recall at 5 23.5% (en→hi 85%, kn→hi 0%, ta→kn 0%); verdict agreement
41.7% strict, 55.0% direction; abstain 36.7%; accuracy when answered 65.8%; p95 82.9 s; 0.11 USD per
check. Cross-language recall gap and 3 inverted gold items: eval/TESTS-TO-DO.md section 5.

## Before the final presentation (Oct 18)

- [ ] Revisit Vertex capacity: Provisioned Throughput versus dynamic shared quota (decision 41). Load-test
      judging-week traffic (several checks in parallel), look at 429 rates in the logs, check current quotas
      for gemini-2.5-pro and flash in the project, then decide with Rohit (it costs money).

## Next step

1. Rohit: phone tests in eval/TESTS-TO-DO.md section 1 (share sheet, push, card in WhatsApp).
2. Latency on slow Vertex days: video extraction alone took 57 s in one run (first call timed out). Look
   at a lower extraction hedge for video, or Provisioned Throughput (decision 41).
4. Gold set v3 after a hand-check (3 items have the conclusion as the claim), re-baseline.
5. Signed-URL upload for shares over 32 MB.
6. Rohit: make `main` the default branch on GitHub (deploys come from main since Oct 9).

