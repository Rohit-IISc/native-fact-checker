# 10. Evaluation and observability

## What we measure

| Metric | How | Target |
| --- | --- | --- |
| Cross-lingual match recall at 5 | Benchmark set of published fact checks. Each claim is translated into a different language from the fact check's own (for example a Hindi fact check queried in Kannada). Run the fact-check sites agent's retrieval only. Hit if the original fact check URL is in the top 5 | Set at first baseline (Oct 11), then no drop over 5 points |
| Verdict accuracy | Gold set: 60 claims with published verdicts (15 per demo language except English, which shares). Run the full pipeline without cache | Baseline first, then no drop over 5 points |
| Abstention quality | Accuracy on answered claims vs NOT_ENOUGH_EVIDENCE rate | Accuracy rises as abstain rate rises |
| Panel agreement | Share of AGREED vs SPLIT | Tracked |
| Latency | p50 and p95 per lane: tier 1 hit, tier 2 hit, full check | Tier 1 under 3 s, tier 2 under 6 s, full under 90 s |
| Cost per check | From `model_calls` | Reported per lane |
| User feedback | Helpful rate | Tracked |

## Datasets

- FactDRIL (multilingual Indian fact checks, paper arXiv 2102.11276). Check on Day 5 whether the dataset is downloadable. If not, build the benchmark from Fact Check Tools API ClaimReview items in hi, ta, kn, id, en (harvested by the seed job), which gives the same structure: claim text, language, publisher URL, rating
- Gold set: hand-picked from published fact checks by BOOM, Alt News, Factly, Newschecker, Vishvas News, YouTurn (Tamil), Mafindo and Tempo (Indonesian). Store the original image or text locally in `gs://{project}-eval`, never in the public repo if licensing is unclear
- Silver set from production: cached verdicts where the panel AGREED, confidence HIGH, and at least one TIER_1 source cited

## Scheduled evaluation (every 3 days)

Cloud Scheduler `0 3 */3 * *` (Asia/Kolkata) triggers Cloud Run Job `eval-runner`:

1. Recall at 5 on 200 benchmark claims across language pairs
2. Verdict regression on the 60 gold claims plus 30 randomly sampled silver claims, cache bypassed
3. Write a row to `eval_runs` and compare with the baseline run
4. Drift rule: if recall at 5 or verdict agreement drops by more than 5 points, or p95 latency rises by more than 30%, set `drift_flag = true`, log an ERROR (alert policy emails Rohit), and write `config/flags.model_review_needed = true`

## Model swap

- `eval-runner --candidate flash=<model_id> --candidate pro=<model_id>` runs the same suite on candidate models and writes a comparison row
- Switching is a human decision: update the `config/models` Firestore doc (runtime override, no deploy) and later `config/models.yaml`
- When Google releases a new Gemini version, run the candidate suite before switching

Cost of one eval run: about 25 US dollars. Recall at 5 uses the free Fact Check Tools API plus cheap translation; only the 90-claim verdict regression runs the full pipeline (doc 13). Keep it every 3 days during the competition, then weekly.

## Observability

- Structured JSON logs to Cloud Logging, every line with `check_id`, `stage`, `uid_hash`
- Structured logs per model call (check_id, stage, model, tokens, latency) and BigQuery `check_runs`, one row per check
- BigQuery tables `check_runs` and `model_calls` (doc 05)
- Log-based metrics and alert policies: error rate over 5% in 15 minutes, p95 full-check latency over 120 s, daily spend over budget fraction
- A Looker Studio dashboard on BigQuery for the deck's benchmark slide: latency by lane, cost per check, verdict mix, languages, cache hit rate
