# Tests still to do

Everything we still have to test before the Oct 11 prototype and the Oct 18 submission. Tick items off as
they pass and write the date and result next to them. Automated suites that already run are listed at the
end for reference. Sources: CLAUDE.md "Definition of done", docs/12-build-plan.md, docs/PROGRESS.md.

## 1. On a real Android phone (only Rohit can do these)

Production: https://ai-builder-2026.web.app. Install the PWA first (Chrome menu, "Add to Home screen").

- [ ] Share a WhatsApp **image** to the PWA from the share sheet: verdict in the post's language, audio,
      sources and a correction card in under 90 s
- [ ] Share a **news article link**, an **X post link** and a **YouTube link**: same as above
- [ ] Share a **short video** (under 3 min): same as above
- [ ] Share the **same image again**, then a **slightly edited copy** (cropped, re-compressed): answer from
      cache in under 5 s
- [ ] **Push notification:** start a check, allow notifications when asked, leave the app; a notification
      "Result ready: {label}" arrives in the UI language; tapping it opens the result. With the result
      screen open, no notification appears
- [ ] **Correction card:** "Share card to WhatsApp" opens the share sheet with the PNG; the card
      looks right in WhatsApp (Hindi, Tamil, Kannada text not broken, colours match the verdict)
- [ ] Audio plays on the phone speaker and is clear (see section 3 for native speakers)
- [ ] Daily limit: the 11th check of the day shows the limit screen with the reset time
- [ ] History lists today's checks and opens each one
- [ ] Public result link opens signed out, in the answer's language, with audio and card
- [ ] A share of 40-50 MB (long video). **Known to fail now:** Cloud Run caps uploads at 32 MB; needs the
      signed-URL upload

## 2. Verdict quality (real models, costs money: `make accept`)

Latest full run: 15/20 (Oct 8 evening). Run with `REPEAT=2` or more; one pass proves little.

- [ ] **01, 02, 03** Kannada flood video: MISLEADING every run (now flips with NOT_ENOUGH_EVIDENCE). Fix
      planned: "this exact video is old" fact checks classified as CONTEXT
- [ ] **01b** flood video as an X screenshot: MISLEADING (gives NOT_ENOUGH_EVIDENCE)
- [ ] **13** BBC news link: TRUE (gives NOT_ENOUGH_EVIDENCE when search finds only tier 3 coverage)
- [ ] **04, 09** flaky: pass in 2 of 2 repeat runs
- [ ] **12** NBT Holi satire: stays MISLEADING (3/3 since Oct 8); the answer text never calls it "false"
- [ ] Every case in all 5 languages: Hindi, Tamil, Kannada, Indonesian, English (CLAUDE.md definition of
      done)
- [ ] 100 real forwards from family groups and fact-check sites (test week, Oct 12-13): note each
      wrong or weak verdict and fix the prompt or code behind it

## 3. People (native speakers)

- [ ] Audio clarity, 3 listeners per language if possible:
      https://claude.ai/artifact/3uKEHUsp5hdXoVFo87SJeo (share it first; it is private)
- [ ] Correction card wording and the push title in Tamil and Kannada ("முடிவு தயார்",
      "ಫಲಿತಾಂಶ ಸಿದ್ಧವಾಗಿದೆ"; config/languages.yaml), written by Claude, not checked by a speaker yet
- [ ] Answer text reads naturally (not like a translation) in each language

## 4. Load and capacity (before the final presentation)

- [ ] 3, 5 and 10 checks at once in production: latency, 429 RESOURCE_EXHAUSTED rate, failed agents
      (Oct 8: 3 at once already caused timeouts in 09, 10a, 10b)
- [ ] Decide Provisioned Throughput versus shared quota with Rohit (decision 41; costs money)
- [ ] Cold start with min instances 0 versus 1 (set 1 for judging week)

## 5. Day 6 operations (deployed Oct 9)

Deployed: eval job `eval-runner` with schedule `eval-every-3-days` (03:00 IST on days 1, 4, 7, ... of the
month), 7 BigQuery views (`factcheck.v_*`), 4 log-based metrics, 5 alert policies emailing Rohit, `build-sa`
and the PWA keys in Secret Manager. Re-run any of it with `make deploy-ops` (needs ALERT_EMAIL).

- [ ] **Rohit: connect GitHub to Cloud Build.** Run `PROJECT_ID=ai-builder-2026 scripts/setup_cloud_build.sh`,
      open the link it prints, authorize and install the Cloud Build app on Rohit-IISc/native-fact-checker,
      then run the script again to create the trigger
- [ ] **Rohit: choose the deploy branch.** The trigger defaults to `claude/upbeat-bardeen-7hz94l`;
      `main` is 18 commits behind. Merge into main and re-run with `BRANCH=main` if you want main
- [ ] Push a small commit: Cloud Build runs gitleaks, ruff, pytest, then deploys backend and frontend
      (Cloud Build history in the console); the site still works afterwards (`make smoke`)
- [ ] A commit with a failing test does **not** deploy
- [ ] Baseline eval stored: `SELECT * FROM factcheck.v_eval_trend` shows the baseline row; Firestore
      `config/eval.baseline_run_id` names it (results in "Eval baseline" below)
- [ ] First scheduled run (Sat Oct 10, 03:00 IST) appears in `v_eval_trend` with `drift_flag` false and
      the baseline id filled in
- [ ] Hand-check 15 gold items (`gs://ai-builder-2026-eval/datasets/v2/gold.jsonl`): is the label mapped from
      the publisher's rating right? (rules in `eval/datasets.py`, decision 42)
- [ ] Alert email arrives: Cloud Monitoring > Alerting > a policy > "Send test notification", check the
      inbox (and spam) of the alert address
- [ ] Dashboard queries return sensible numbers with `env = 'prod'`: `v_daily`, `v_lanes_daily`
      (T1 rows appear after the next real repeat share; tier 1 hits are logged since Oct 9),
      `v_stage_latency_7d`, `v_verdict_mix`, `v_model_calls_daily`
- [ ] **Rohit: Looker Studio dashboard** on those views for the deck (latency by lane, cost per check,
      verdict mix, languages, cache hit rate); Looker Studio needs your Google login
- [ ] **Rohit: billing budget** (docs/13: 750 with alerts at 50%, 90%, 100%). The billing account
      "ai-builder-cup" is in INR and this login cannot read its budgets; set it in Billing > Budgets
- [ ] Silver set: stays empty until production has verdicts the panel AGREED on with HIGH confidence
      and a tier 1 source; check `n_silver` grows in later runs

## 6. Not built yet, so not testable yet

- [ ] Signed-URL upload for shares over 32 MB

## 7. Before submission

- [ ] `make check-models`: every model ID in config/models.yaml still exists in Vertex AI
- [ ] Demo cache seeded with the demo shares
- [ ] Judge accounts on the allowlist (config/limits.yaml `judge_allowlist`)
- [ ] Repo made public (Rohit's go-ahead) with nothing secret and nothing from `samples/` in git history
- [ ] Dry run of the whole demo on the phone, end to end

## Already automated (run these after every change)

| Command | What it covers | Cost |
| --- | --- | --- |
| `make test` | 271 backend tests offline (source policy, cache keys, quota, link ladder, SSRF guard, panel merge, card, push, eval logic, recorded pipeline replays) plus the frontend type check | Free |
| `make accept` | The acceptance cases in `tests/acceptance/` against real models | About $2 per full run |
| `make smoke` | Production through Pub/Sub, including audio, then cleans up | A few cents |
| `make eval` | The eval locally (`ARGS="--gold-n 10 --silver-n 0"` for a small one); the scheduled job runs the full size | 7 to 10 USD full |
