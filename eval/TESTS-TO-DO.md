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

## 5. Not built yet, so not testable yet

- [ ] Eval runner (`eval/runner.py` is a stub): recall at 5 and verdict regression, first baseline stored
- [ ] Cloud Scheduler: eval every 3 days
- [ ] Alerts (latency, error rate, cost)
- [ ] BigQuery view of latency and cost per check (rows are already written to `factcheck.check_runs`)
- [ ] Cloud Build trigger: deploy on push to main (`cloudbuild.yaml` exists, no trigger)
- [ ] Signed-URL upload for shares over 32 MB

## 6. Before submission

- [ ] `make check-models`: every model ID in config/models.yaml still exists in Vertex AI
- [ ] Demo cache seeded with the demo shares
- [ ] Judge accounts on the allowlist (config/limits.yaml `judge_allowlist`)
- [ ] Repo made public (Rohit's go-ahead) with nothing secret and nothing from `samples/` in git history
- [ ] Dry run of the whole demo on the phone, end to end

## Already automated (run these after every change)

| Command | What it covers | Cost |
| --- | --- | --- |
| `make test` | 264 backend tests offline (source policy, cache keys, quota, link ladder, SSRF guard, panel merge, card, push, recorded pipeline replays) plus the frontend type check | Free |
| `make accept` | The acceptance cases in `tests/acceptance/` against real models | About $2 per full run |
| `make smoke` | Production through Pub/Sub, including audio, then cleans up | A few cents |
