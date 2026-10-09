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
- [ ] A share of 40-50 MB (long video) from the phone: the PWA uploads it straight to Cloud Storage
      (built Oct 9) and the verdict arrives as for small videos. Live-tested from the dev box: a 37.7 MB
      video PUT in 0.6 s via a signed URL, read back intact, refused for another user
- [ ] A share just under 24 MB still goes the old way (one request) and works

## 2. Verdict quality (real models, costs money: `make accept`)

Latest full run: 15/20 (Oct 9 evening, slow Vertex: web search and translation timeouts in 03, 04, 01b; 13 known; 15 see below). Best Oct 9: 18/20. Run with
`REPEAT=2` or more; one pass proves little.

- [ ] **01, 02, 03** Kannada flood video: MISLEADING every run. Oct 9 fixes: the claim comes from the
      sharer's caption, the printed "DELHI संकट मे" is searched as text, "this exact video is from
      elsewhere" is CONTRADICTS. 2/2 MISLEADING on a REPEAT=2 run; fails only when extraction runs
      over budget on slow Vertex days
- [ ] **01b** depends on web search alone (the Fact Check Tools API has no match): 0/2 when web search
      timed out on Oct 9 afternoon. Re-test on a normal day
- [ ] **15** thin local claim gave MISLEADING at 90% on Oct 9 (panel read old crocodile sightings, all
      CONTEXT, as "real event, wrong date"). Proposed code guard (needs Rohit, it changes verdict logic): a
      decisive label backed only by CONTEXT items, with no CONTRADICTS or SUPPORTS item, becomes
      NOT_ENOUGH_EVIDENCE
- [x] **Answer wording matches the label** (Oct 9, composer 1.3): 0 of 6 MISLEADING answers call the post false
- [ ] **10a** Mumbai flyover bus (AI image): FALSE (Oct 9 gave MISLEADING; it passed before)
- [ ] **13** BBC news link: TRUE (gives NOT_ENOUGH_EVIDENCE when search finds only tier 3 coverage)
- [ ] **04, 09** flaky: pass in 2 of 2 repeat runs
- [ ] **12** NBT Holi satire: stays MISLEADING (1/2 on slow Oct 9 afternoon: the miss ran over budget)
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

- [x] **Rohit: connect GitHub to Cloud Build** (Oct 9). Trigger `deploy-on-push` created
- [x] **Deploy branch is `main`** (Oct 9, Rohit): working branch merged into main; the trigger watches `^main$`
- [ ] **Rohit: make `main` the default branch on GitHub** (Settings > Branches); it is still
      `claude/upbeat-bardeen-7hz94l`, so new clones and PRs start from the old branch
- [ ] Push to main: Cloud Build runs gitleaks, ruff, pytest, then deploys backend and frontend
      (Cloud Build history in the console); the site still works afterwards (`make smoke`).
      First run: the Oct 9 merge push (result below)
- [ ] A commit with a failing test does **not** deploy
- [x] Baseline eval stored (Oct 9): `factcheck.v_eval_trend` shows it; Firestore `config/eval.baseline_run_id`
      names it (results in "Eval baseline" below)
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

### Eval baseline (Oct 9, run `20261009-063001-baseline`, dataset v2, 33 min, 6.57 USD)

| Metric | Baseline |
| --- | --- |
| Recall at 5, overall (200 claims) | 23.5% |
| en→hi / id→en / hi→ta / kn→hi / ta→kn | 85% / 27.5% / 5% / 0% / 0% |
| Verdict agreement, strict / direction (60 gold) | 41.7% / 55.0% |
| Abstain (NOT_ENOUGH_EVIDENCE) | 36.7% |
| Accuracy when answered | 65.8% |
| Full check p50 / p95 | 51.8 s / 82.9 s |
| Cost per check | 0.11 USD (audio off) |

By language (strict / direction of 12): hi 6/8, ta 2/5, kn 3/4, id 6/8, en 8/8. Tamil abstains most (7 of 12).

### Eval baseline v3 (Oct 9, run `20261009-090459-baseline`, the current baseline)

Dataset v3 (57 gold), with the cross-language search. Drift is measured against this run.

| Metric | v2 baseline | v3 baseline |
| --- | --- | --- |
| Recall at 5 (200 claims) | 23.5% | 48.0% |
| Verdict agreement, strict / direction | 41.7% / 55.0% | 54.4% / 71.9% |
| Abstain | 36.7% | 22.8% |
| Accuracy when answered | 65.8% | 70.5% |
| Full check p50 / p95 | 51.8 s / 82.9 s | 66.7 s / 93.5 s (shared Vertex quota with make record during the run) |
| Cost per check | 0.110 USD | 0.097 USD |

- [ ] First scheduled run on v3 (Sat Oct 10, 03:00 IST, nothing else running): latency close to 50 s p50? If
      it is much lower than the v3 baseline, re-baseline so the 30% latency drift rule bites

Findings to test and fix:
- [x] **Cross-language recall was near zero for Indian languages** (fixed Oct 9). The fact-check agent now
      also searches without a language filter, and the extractor (1.12) writes one query each in the other
      Indian demo languages (hi, ta, kn), because the API matches words. Recall-only eval, dataset v2:
      23.5% -> 41.5% and 45.5% on two runs (kn->hi 0 -> 35-40%, hi->ta 5 -> 35-37.5%, ta->kn 0 -> 22.5%;
      id->en varies 37.5-70% between runs: Flash writes different queries each time). Recall at 15
      (what the agent shows its classifier): 50.5%. `make accept`: 18/20 (see section 2)
- [x] **Gold labels with inverted claims** (fixed Oct 9, dataset v3). Gold candidates are checked by Flash
      for form (claim as circulated vs the fact-checker's finding or a question; 491 of 1996 dropped),
      then Claude hand-checked all 60 and removed 3 more Kannada findings: 57 items. New baseline on v3
      (see "Eval baseline v3" below). Rohit: spot-check 15 of
      `gs://ai-builder-2026-eval/datasets/v3/gold.jsonl` if you have time
- [ ] TRUE claims abstain 7 of 12: expected when only tier 3 coverage is found (as case 13); look at
      whether more tier 2 news sites belong in config/source_tiers.yaml (Rohit decides tiers)

## 6. Before submission

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
