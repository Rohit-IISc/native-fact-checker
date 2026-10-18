# Progress

Updated after every task (see CLAUDE.md, "How to work"). Newest state only; history is in git.

**Last updated:** Fri Oct 16, 2026, evening (submission freeze)
**Build-plan day:** Test week; **submission freeze** (tag `submission-freeze`): no model or pipeline changes before Oct 18.
**Last updated:** Fri Oct 16, 2026
**Build-plan day:** Day 6 work on Fri Oct 9: Days 0 to 5 done; Day 6 (measure) deployed; pushes to main deploy via Cloud Build.
**Deployed:** https://chckr.web.app (Firebase Hosting site `chckr`) -> Cloud Run `factcheck-api` (asia-south1). The old https://ai-builder-2026.web.app redirects every page there and still serves `/api` (old links, cards and audio keep working).
**Audio samples for native speakers:** https://claude.ai/artifact/3uKEHUsp5hdXoVFo87SJeo (private; share it).



## Oct 18: submission day

- Phase A (branch `scoring/evidence-score`, not live): evidence score in `verify/source_policy.py`, weights in
  `config/source_tiers.yaml` (initial, to be calibrated), replay in `docs/replay-evidence-score.md`. Final
  config: 0 blocks, 3 NEE to the Critic (1 matches gold). Grouping by embeddings above 0.9 merges independent
  outlets; a fact-check rating can belong to a different claim. Live gating waits until after 7 Nov.
- Phase B (main): demo verdicts pinned (18 cases, no expiry); `seed_demo_cache.py --check` as Cloud Run Job
  `demo-cache-check`, daily 06:00 IST, media from private `gs://ai-builder-2026-eval/demo-media/`; 12 junk
  verdicts deleted (stubs, early tests); min instances 1 (deploy script default during judging); README for
  judges and Apache 2.0 LICENSE; examples API live, "Try an example" UI on branch `ui/try-example` (preview).
- gitleaks: 58 commits, no leaks. check-models and TTS OK.
- After submission: tag `submitted`; only critical fixes on main until 7 Nov. Set min instances back to 0
  after 7 Nov (`deploy_backend.sh` default) and pause `demo-cache-check-daily`.

## Oct 16 night: UI brief rounds 1-3 live (Bazaar Bright), sign-in on chckr.web.app

- Live on chckr.web.app: landing with instant language chips; header language button (language list only);
  dock Home, Checks (running check only), Trending, History, Settings (gear: display language dropdown,
  sign out, delete account, privacy, terms); Home (paste box, real checks left, 7 input tiles, WhatsApp line,
  Recent checks from all users); Checking (ring, agent tiles, steps); Result (banner with real reviewer and
  source counts, audio player with duration, For/Against/Sources, tabs, share buttons); Daily limit; History
  (real counts, chips); Trending (24 h, widens to 7 days below 3 items).
- Composer 1.4 writes AI-generation signals in the answer language (make record 19/20, 01b the known flaky
  case). Tag `submission-freeze` moved to 3c31562.
- Sign-in: authDomain is the page's own host (chckr.web.app, preview channels), same-window redirect on those
  hosts (the popup looped on Android with the app installed); the service worker skips /__/. Firebase browser
  key restricted to our referrers (exact preview host: Google does not match mid-host wildcards).
- `scripts/check_secrets.sh` as pre-commit hook (`make hooks`); history scanned clean.
- Waiting on Rohit: "delete" for cache junk (item 10). Then: Lighthouse and share-target check.

## Oct 16 evening: UI brief round 1 live, privacy and terms pages

- Round 1 (landing with instant language chips, yellow header with language sheet, five-item dock, Trending v1,
  Checks = the check now running) approved by Rohit and deployed. Rounds 2 (Home, Checking, Result, AI-signal
  language fix) and 3 (Daily limit, History, Trending polish) next, each on preview channel `bazaar-bright` first.
- New read-only API: `PUT /v1/me/language`, `GET /v1/me/history/stats`, `GET /v1/feed/recent`, `GET /v1/feed/trending`
  (`backend/app/feed.py`, limits in `config/limits.yaml` `feed`).
- `/privacy` and `/terms` public pages in 5 languages (`frontend/src/screens/Legal.tsx`), linked from landing,
  consent screen and the language sheet. In-app "Delete my account" in the language sheet.
- `DELETE /v1/me` now also deletes the user's check records and Firebase Auth record (api-sa has
  `roles/firebaseauth.admin`).
- Waiting on Rohit: OAuth client and consent-screen settings (item 9), "delete" for cache junk (item 10).

## Done

- **Oct 16 evening, live at https://chckr.web.app** (decision 49): Bazaar Bright design and CHCKR name merged;
  old ai-builder-2026.web.app redirects every page (301, path kept) and still serves `/api`. Firebase Auth
  domains, CORS (API and media bucket) and PUBLIC_BASE_URL updated; the reCAPTCHA key allows all domains.
  Correction-card fix: Latin words on hi/ta/kn cards drew as boxes (fonts per script run now). All 32
  cards of the 16 seeded verdicts regenerated with the new URL; 25 stored audio links moved to the new host
  (15 pointed at a Codespace from the seed run; the seed script now forces the production URL). Seed
  report: all 20 demo shares answer from cache. Smoke test passed.

- **Final config (decision 48, frozen Oct 16):** extractor gemini-2.5-flash (512 thinking tokens); web search,
  other agents, packager and composer gemini-3.8-flash; Judge, Critic and revision gemini-3.1-pro-preview;
  fallbacks the other generation (docs/02 "Models per stage"). Judge limit 45 s. Critic on every check.
  Final `make accept`: 16/20, avg 46.2 s. Fails: 01, 02, 03 and 13. **Known ~2-in-3 case:** 01 (and 02/03,
  which reuse its verdict) depends on web search finding the PTI or Quint "old 2022 Bengaluru video" fact
  checks; when it does not, the panel abstains (NOT_ENOUGH_EVIDENCE). Search retrieval variance, not config.
  13 (BBC link) is similar for TRUE news.
- **Demo cache seeded in production (Oct 16)** with `scripts/seed_demo_cache.py`, each verdict from a real
  pipeline run (uid demo-seed; 01 from a production check of the same video at 12:55): all 20 acceptance
  shares answer from cache with an expected label. 01, 01b, 02, 03, 04, 12 MISLEADING; 05, 07, 09, 10a,
  10b, 14, 90 FALSE; 06, 06b SCAM; 08, 13 TRUE; 15 NOT_ENOUGH_EVIDENCE; 11, 16 NOT_CHECKABLE.
  NOT_ENOUGH_EVIDENCE verdicts expire after 3 days: rerun the script (report mode, then `--seed`) before
  judging.
- Cost review (Oct 16): per-lane costs and deck notes in docs/14; grounding is about half of a full check
  at list price but inside the free 5,000 queries a month at current volume.
- **Oct 16, branch `ui/bazaar-bright` (not merged, not on main):** Bazaar Bright frontend design from the
  kit in `artifacts/` (patch applied cleanly), app renamed to **CHCKR** everywhere (UI in all five
  languages, tab title, PWA manifest, correction-card name in `config/languages.yaml` and `card.py`),
  logo and favicon from `artifacts/chckr_logo_hd_v2.png` (full logo on sign-in; eagle-only crop for the
  header, favicon and app icons; colours untouched). 15 new strings translated into hi/ta/kn/id
  (**native-speaker review needed for Hindi, Tamil, Kannada**). Fixes found at 360 px: header too wide (one
  row now; duplicate History link removed, the dock has it), kit CSS cropped the logo, Tamil tile labels
  collided (tiles now size to their label), two colours below 4.5:1 darkened, press animation off under
  reduced motion, tile group got `role="group"`, domain monograms ("thequint.com" read "TC").
  Preview (real backend and production data, expires Oct 23):
  https://ai-builder-2026--bazaar-bright-3p5hkmt8.web.app . Waiting for Rohit's go-ahead.

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
- Large shares (decision 45): `POST /v1/uploads` signs a 15-minute PUT URL to `staged/{uid hash}/{id}` in the
  media bucket (`intake/uploads.py`); `POST /v1/checks` takes `upload_ids`; the PWA uses it above 24 MB.
  Live-tested: 37.7 MB PUT in 0.6 s, read back, refused for another user. Bucket CORS in deploy_backend.sh.
- Case 01 fixes and answer wording (extractor 1.13, classify 1.4, factcheck 1.5, composer 1.3; OCR text is
  searched by code). Cross-language fact-check search (extractor 1.12 regional queries, unfiltered search).
  Eval gold v3 with a claim-form filter and hand-check; new baseline on v3.
- Models (decision 47): Gemini 3.8 Flash and 3.1 Pro preview primary, 2.5 as fallback after a final 429/5xx.
  429 logging (model_calls error_code, rate_limited, created_at; view v_rate_limits). Priority PayGo flag
  (off; not served to this project on Oct 9). Load test: 10 checks at once all done under 81 s.
- `eval/TESTS-TO-DO.md`: every test still to do (phone, verdict quality, native speakers, load, unbuilt).
- Day 5 audio (`backend/app/output/tts.py`): Gemini TTS, voice per language, MP3 via ffmpeg, stored in the
  outputs bucket, served by `GET /v1/results/{id}/audio`. Generated after DONE (TTS takes 18-24 s);
  the UI shows "audio is being prepared" until the player appears. Verified by round-trip transcription
  in all 5 languages and in production through Hosting.

## In progress

- Nothing mid-edit.

## Broken or risky

Latest `make record` (Oct 9 night, CONTEXT-only guard shipped, decision 46; classify 1.5 and factcheck 1.6 see
the post's media; media provenance 1.3): 14/20, avg 51.7 s, $2.26. 13 passed (TRUE) for the first time; 15
passes. Fails: 01/02/03 (one abstention: The Quint's check classed CONTEXT; 01 is MISLEADING in 3 of 4
runs where search finished), 01b (FALSE, want MISLEADING), 06b and 12 (judge or web search timeouts).
Before that, `make accept` (Oct 9 evening, after the large-upload change, which does not touch the pipeline):
15/20, avg 57.8 s, $1.90. Fails: 01b, 03, 04 (web search or translation timeouts), 13 (known), 15 (MISLEADING
at 90% from CONTEXT-only evidence; guard proposed, needs Rohit).
Before that, `make accept` (Oct 9 afternoon, after the case 01 and wording fixes): 14/20, avg 60.7 s, $2.04, on a
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
- Looker Studio dashboard and the billing budget need Rohit (eval/TESTS-TO-DO.md section 5).

Eval baseline (current: Oct 9, dataset v3, 57 gold, with the cross-language search): recall at 5 48.0%;
verdict agreement 54.4% strict, 71.9% direction; abstain 22.8%; accuracy when answered 70.5%; p95 93.5 s
(inflated: shared quota with make record); 0.097 USD per check. The v2 baseline (23.5% recall, 41.7% strict)
is kept for history. Details: eval/TESTS-TO-DO.md section 5.

## Before the final presentation (Oct 18)

- [ ] Revisit Vertex capacity: Provisioned Throughput versus dynamic shared quota (decision 41). Load-test
      judging-week traffic (several checks in parallel), look at 429 rates in the logs, check current quotas
      for gemini-2.5-pro and flash in the project, then decide with Rohit (it costs money).

## Next step

- **Morning of Sun Oct 18, before submitting:** rerun `scripts/seed_demo_cache.py` (report, then `--seed`):
  case 15's NOT_ENOUGH_EVIDENCE verdict expires 3 days after Oct 16.
- Rohit: phone checklist in eval/TESTS-TO-DO.md section 1b (reinstall from chckr.web.app first).

- Frozen: no model or pipeline changes. Remaining: UI changes and the app URL (Rohit), merge of
  `ui/bazaar-bright` when approved, deck and video, phone tests, re-seed the demo cache before judging.

0. Rohit: review the Bazaar Bright preview and give the go-ahead (or changes); then merge `ui/bazaar-bright`
   into main (deploys) and redeploy the backend for the CHCKR name on the correction card. Open questions:
   self-hosting Nunito for offline use; Gemini 3 recall drift (Oct 9 eval) still to investigate.
- (Oct 16 fixes on main) A 3.1 Pro judge call and its same-model hedge both stalled past 30 s (2 of 24 judge
  calls since the switch), so the check fell back to NOT_ENOUGH_EVIDENCE and showed "nothing found" next to
  PTI's tier 1 fact check. Now: the hedge duplicate goes to the fallback model (2.5), and a judge failure
  still lists evidence for and against by stance. Vision got one 401 in production with a cached token: it
  now refreshes and retries once. Follow-up: video extraction on 3.8 Flash takes 18-28 s (2.5: 10-13 s);
  record whether the hedge fired (it logs at INFO only).

1. Rohit: phone tests in eval/TESTS-TO-DO.md section 1 (share sheet, push, card in WhatsApp).
2. Latency on slow Vertex days: video extraction alone took 57 s in one run (first call timed out). Look
   at a lower extraction hedge for video, or Provisioned Throughput (decision 41).
3. Case 01 stability with the guard: the fact-check agent sometimes still calls "this same video is old"
   CONTEXT. Next idea: pass the media's earliest appearance from media provenance into the classifiers.
4. Rohit: phone test of a 40-50 MB share (direct upload, eval/TESTS-TO-DO.md section 1).
5. Rohit: make `main` the default branch on GitHub (deploys come from main since Oct 9).

