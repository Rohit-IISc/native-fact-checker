# 13. Cost estimate (for the deck's "Estimated implementation cost" slide)

All figures in US dollars. Prices checked on Oct 4, 2026 from public listings; confirm on the Vertex AI pricing page on Day 0 and update `config/models.yaml`, because the code computes live cost from those numbers.

## Unit prices used

| Item | Price used | Note |
| --- | --- | --- |
| Gemini Flash (3.6 to 3.8 Flash) | 0.75 per 1M input, 3.75 per 1M output | Introductory price through Dec 31, 2026; standard 1.50 / 7.50 from Jan 1, 2027 |
| Gemini Pro (3.1 Pro preview) | 2.00 per 1M input, 12.00 per 1M output | Up to 200K input tokens |
| Grounding with Google Search | 5,000 queries per month free across Gemini 3 models, then 14 per 1,000 | Biggest single cost line per check |
| Cloud Vision web detection | about 3.50 per 1,000 images after 1,000 free per month | Verify |
| Gemini TTS | about 0.01 per 40 s answer | Verify on the TTS pricing page |
| Fact Check Tools API | Free | |
| Embeddings | Under 0.0001 per claim | |
| Video input | about 100 tokens per second at low resolution, 300 at default, plus 32 per second for audio | 3 min video at low resolution is about 18K tokens |

## Cost per check (estimates, thinking tokens counted as output)

| Stage | Tokens in / out | Cost |
| --- | --- | --- |
| Extractor (Flash, 1 image) | 5K / 2K | 0.011 |
| Web search agent (Flash) + 4 grounded queries | 4K / 2K + 4 queries | 0.011 + 0.056 |
| Fact-check sites agent (Flash) | 4K / 1.5K | 0.009 |
| Source credibility agent (Flash) | 3K / 1K | 0.006 |
| Media provenance agent (Flash) + Vision | 4K / 1.5K + 1 image | 0.009 + 0.004 |
| Packager (Flash) | 10K / 2.5K | 0.017 |
| Judge (Pro) | 8K / 3K | 0.052 |
| Critic (Pro) | 10K / 2K | 0.044 |
| Judge revision, 30% of checks (Pro) | 12K / 2K | 0.014 |
| Composer (Flash) | 4K / 2.5K | 0.012 |
| TTS | 1 answer | 0.010 |
| Full check, image or text | | about 0.25 |
| Full check, 3 min video | adds about 18K input tokens and keyframe Vision calls | about 0.28 |
| Tier 1 cache hit, same language | Firestore reads only | about 0.0005 |
| Tier 2 cache hit | embedding + near-match check | about 0.002 |
| Cache hit, new language | translate + TTS | about 0.02 |

Where the money goes in a full check: the review panel (Judge, Critic, revision) is about 44%, grounding about 22%.

## Prototype period (Oct 4 to Oct 31)

| Line | Volume | Cost |
| --- | --- | --- |
| Development and testing | about 1,000 full checks | 250 |
| Evaluation runs (verdict regression on 90 claims each; recall at 5 uses the free Fact Check Tools API) | 8 runs at about 25 | 200 |
| Judging and demo traffic | about 1,500 checks, half from cache | 190 |
| Free grounding allowance | 5,000 queries per month | minus up to 70 |
| Cloud Run (min 1 instance for 2 weeks), Firestore, Storage, BigQuery, Pub/Sub, Hosting | | under 40 |
| Total | | about 600 to 650 |

Set the GCP budget at 750 with alerts at 50%, 90% and 100%. The global daily cap on new investigations (doc 08) is the hard stop.

## At scale (for the deck)

Assumption: 100,000 checks per day, 60% answered from cache (Cofacts answered about 76% of incoming messages from its database, so 60% is conservative once the cache warms).

| Scenario | Full checks per day | Cost per day | Blended cost per check | Per 1,000 checks |
| --- | --- | --- | --- | --- |
| Prototype design as built | 40,000 | about 10,000 | about 0.10 | about 100 |
| With planned optimizations | 40,000 | about 3,000 | about 0.03 | about 30 |

Planned optimizations (all on the roadmap, none needed for the prototype):
1. LLM router calls only the sub-agents a claim needs (text claims skip media provenance; most claims need 2 grounded queries, not 4)
2. Critic runs only when Judge confidence is under 90 or the label is FALSE, MISLEADING or SCAM
3. Context caching for the long system prompts
4. Flex or batch pricing for evaluation runs and background retries
5. Cache hit rate rises with usage; every new verdict serves every later user in every language
6. Infrastructure scales to zero when idle (Cloud Run, Firestore, Pub/Sub), so there is no fixed server cost

Revenue paths to cover this (for the future slide): B2B API for platforms, telcos, newsrooms and banks; government and public-interest grants for digital literacy; free tier for citizens.
