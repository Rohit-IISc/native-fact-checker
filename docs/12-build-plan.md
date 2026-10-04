# 12. Build plan: Oct 4 to Oct 11, then test week

Working rhythm: Claude Code builds on Rohit's laptop; each day ends with a deployed, working slice.

| Day | Date | Goal | Done when |
| --- | --- | --- | --- |
| 0 | Sun Oct 4 | Setup | GCP project, Firebase, bootstrap script run, repo created with this folder, backend and frontend skeletons, `/healthz` deployed to Cloud Run, PWA shell on Hosting with Google sign-in |
| 1 | Mon Oct 5 | Text lane end to end | Paste text, extractor returns claims, stub verdict, Firestore progress drives the live screen. Measure extraction latency on 10 sample videos to fix timeouts |
| 2 | Tue Oct 6 | Media and links | Image, video, audio upload; share target from WhatsApp works on an Android phone; link fetch ladder; tier 1 cache |
| 3 | Wed Oct 7 | Sub-agents | Web search, fact-check sites, source credibility, media provenance agents with timeouts; source tiers YAML; seed_sources.py run once; tier 2 cache with near-match check; threshold tuned on 50 pairs |
| 4 | Thu Oct 8 | Panel | Packager, Judge, source policy, Critic, revision, split handling; unit tests for policy and panel merge |
| 5 | Fri Oct 9 | Answer | Composer in 5 languages, Gemini TTS, correction card with Indic text, result page, history, FCM push, quota and App Check |
| 6 | Sat Oct 10 | Measure | BigQuery logging and cost, eval runner and first baseline, Cloud Scheduler, alerts, Cloud Build trigger |
| 7 | Sun Oct 11 | Ship | All 15 acceptance cases pass in all 5 languages, deployed, demo cache seeded |

If a day slips, cut in this order (last cut first): history screen, public result page, correction card (keep audio), Kannada TTS fallback work, eval scheduling (run manually instead). Never cut the source policy, the Critic, or the cache.

## Test and polish week

| Date | Work |
| --- | --- |
| Mon Oct 12 to Tue Oct 13 | Run 100 real forwards from family groups and fact-check sites; fix prompt failures; tune thresholds; native speakers (3 per language if possible) rate audio clarity |
| Wed Oct 14 | Stretch: satellite verifier for floods and fires if everything is green |
| Thu Oct 15 | Final benchmark run for the deck; screenshots in all 5 languages |
| Fri Oct 16 | Demo video recording (script in doc 14); deck filled |
| Sat Oct 17 | Repo cleanup and public; min instances to 1; judge accounts on allowlist; dry run of the submission |
| Sun Oct 18 | Submit |
