# 16. Decisions log (source of truth)

Decided with Rohit and Shubham on Oct 4, 2026. If anything elsewhere conflicts, this wins.

| # | Topic | Decision |
| --- | --- | --- |
| 1 | Scope | Workflow diagram scope. Sub-agents: web search, fact-check sites, source credibility, plus media provenance (added by Claude because reverse image search is the only way to catch old riot and war photos reused with new captions, which the team named as the most common case). Bank SMS, phishing, scam checker out |
| 1b | Satellite | Stretch goal on Oct 14, narrow to fires and floods (doc 15) |
| 2 | Extractor output | Claims in original language and English; search both |
| 3 | Verdict scale | 5 labels: TRUE, FALSE, MISLEADING, SCAM, NOT_ENOUGH_EVIDENCE. Plus NOT_CHECKABLE status with type |
| 4 | Review | Judge plus Critic, both Gemini Pro. Disagreement leads to one revision; a remaining split gives NOT_ENOUGH_EVIDENCE with all evidence for and against. AI-generation questions always show signals both ways |
| 5 | Correction card | In scope, drawn by code (Pillow), no generated imagery |
| 6 | Cache tiers | Tier 1 hash before extraction, tier 2 semantic after |
| 7 | Near match | Goes through a quick Flash check |
| 8 | Expiry | LIVE_EVENT active 90 days then archived; EVERGREEN never expires; archived verdicts used as context evidence. Every claim stores event date and claimed date; date mismatch gives MISLEADING |
| 9 | New language on cached verdict | Translate and TTS on the fly, store it |
| 10 | Vector store | Firestore vector search |
| 11 | Link fetching | Ladder: YouTube URL straight to Gemini, X oEmbed, Meta oEmbed, Open Graph and page text, then ask for screenshot. See below |
| 12 | Limits | Video and audio 3 min, 50 MB per share, 10 images per share |
| 13 | Multi-claim | One verdict per claim, max 3 claims per share |
| 14 | Non-checkable | Return NOT_CHECKABLE with the type (opinion, satire, joke, greeting and so on) |
| 15 | Answer language | Language of the forwarded content |
| 16 | Languages | Hindi, Tamil, Kannada, Indonesian, English (Telugu removed) |
| 17 | TTS | Gemini TTS preferred; Chirp 3 HD fallback for Kannada if preview quality is poor |
| 18 | Orchestration | Fixed parallel fan-out now; LLM router later for cost |
| 19 | Source credibility | No hand-curated bad list. Offender list derived from published fact checks (ClaimReview) and auto-updated weekly plus from our own agreed verdicts. Domain age and lookalike checks. Badges near-zero weight |
| 20 | Models | All Gemini. Flash for sub-agents, Pro for Judge and Critic |
| 21 | Latency | 90 s base; extraction timeout scales with media length; on overrun return NOT_ENOUGH_EVIDENCE with partial evidence and retry once in background |
| 22 | Escalation | Dropped for now |
| 23 | Platform | Android-first PWA |
| 24 | Progress | Live progress screen plus push |
| 25 | Stack | React + Vite PWA, Python + ADK on Cloud Run |
| 26 | Sign-in | Mandatory Google sign-in + App Check + server quota + global daily cap (doc 08) |
| 27 | History | Yes, behind sign-in |
| 28 | API | Documented only |
| 29 | Sources | No verdict without credible sources, enforced in code. Social posts never sources. Sources cited aloud in audio; links under the audio |
| 30 | Retention | Raw media deleted after 24 hours; consent on first use |
| 31 | Quota | 10 checks per user per day |
| 32 | Region | asia-south1 (Mumbai); Gemini via global endpoint. Project ID and credits set up by Rohit later |
| 33 | Infra | gcloud and firebase CLI scripts, not Terraform |
| 34 | CI/CD | Cloud Build on push to main |
| 35 | Evaluation | Built in; every 3 days; recall at 5 on FactDRIL or ClaimReview-derived set plus verdict regression; drift alert; human-approved model swap |
| 36 | Observability | BigQuery, Cloud Logging, Cloud Trace from day one |
| 37 | Prompts | Drafted in `prompts/` |
| 38 | Build | Single laptop, single Claude Code workspace |
| 39 | Dates | Prototype Oct 11, test week Oct 12 to 17, submit Oct 18 |
| 40 | Media observations (Oct 8, Rohit) | The judge may see neutral facts printed or visible on the shared item itself (satire or parody tags such as "बुरा न मानो होली है", newspaper masthead dates, outlet watermarks, channel logos with on-screen dates, visible signs of editing), never the post's claim, caption or persuasive wording. The extractor lists them as `media_markers`; code adds one `media_itself` item per claim (NOT_A_SOURCE, CONTEXT). They can decide what kind of item it is (satire shared as news is MISLEADING) but the source policy ignores them: a decisive label still needs external sources. Refines rule 3 of CLAUDE.md |
| 41 | Model capacity (Oct 8, Rohit) | Stay on Vertex dynamic shared quota with 429 backoff. No Provisioned Throughput for now; revisit before the final presentation |
| 42 | Eval datasets (Oct 9, Claude, for Rohit to review) | Benchmark and gold come from Fact Check Tools API ClaimReview items (docs/10's fallback to FactDRIL), harvested in hi, ta, kn, id, en and frozen as versions in `gs://{project}-eval/datasets/` (v2 is the first used; v1 was dropped before use because Indonesian "sesat" and "sebagian benar" were mislabelled). Gold labels are mapped from the publishers' ratings by rules in `eval/datasets.py`, not hand-picked; "Half true" counts as MISLEADING. Two agreement numbers: strict (same label) and direction (both FALSE/MISLEADING/SCAM, or both TRUE), because publishers split FALSE and MISLEADING differently from us. Recall at 5 is strict: only the exact fact-check URL counts, other publishers' checks of the same claim do not. v3 (Oct 9): gold candidates whose text is the fact-checker's finding or a question are dropped by a Flash check (prompts/13_eval_claim_form.md, 491 of 1996), then a hand-check removed 3 more Kannada items; 57 gold items, new baseline on v3 |
| 43 | Eval size and cost (Oct 9) | docs/10's full size (200 recall claims, 60 gold, 30 silver) every 3 days at 03:00 IST. Measured about 0.11 USD per pipeline item with audio off, so 7 to 10 USD a run (docs/10 estimated 25). Eval runs never touch the production cache and do not write check_runs |
| 44 | Deploy on push (Oct 9, Rohit) | Cloud Build trigger `deploy-on-push` (asia-south1) deploys every push to `main`, running as a dedicated `build-sa` (not the default compute account, which has Editor). The working branch `claude/upbeat-bardeen-7hz94l` was merged into main (fast-forward) on Oct 9; work lands on main from now on |
| 45 | Large shares (Oct 9) | Cloud Run refuses request bodies over 32 MB, so shares over 24 MB go from the PWA straight to the media bucket with a 15-minute signed PUT URL (`POST /v1/uploads`); the check sends upload ids. Objects sit at `staged/{uid hash}/{upload id}` (the path proves ownership), are deleted as soon as a check reads them, and the bucket's 1-day lifecycle removes any left (rule 5). The bucket allows PUT from the app's origins (CORS, set by deploy_backend.sh) |
| 46 | Background-only verdicts (Oct 9, Rohit) | The source policy also requires at least one cited item with stance SUPPORTS or CONTRADICTS; a decisive label backed only by CONTEXT becomes NOT_ENOUGH_EVIDENCE. Case 15 had MISLEADING at 90% from old crocodile sightings (2010, 2017). Stance prompts now agree on old media: an earlier appearance of the same media elsewhere CONTRADICTS a claim about it (media provenance 1.3, classify 1.4, factcheck 1.5) |
| 47 | Models (Oct 9, Rohit) | Primary: gemini-3.8-flash (thinking low; extractor medium) and gemini-3.1-pro-preview (thinking medium); fallbacks gemini-2.5-flash and gemini-2.5-pro after a final 429 or 5xx. Back-to-back make accept: 19/20 at 44.3 s average vs 13/20 at 59.4 s on 2.5, 1 Flash timeout vs 10. Model cost about 12% higher (0.005 USD more per full check) at 3.8 Flash's introductory rate until Dec 31, 2026; 3.1 Pro uses about a third of 2.5 Pro's output and thinking tokens. Risk: 3.1 Pro is a preview model, and both 3.x models were slow on Oct 5; watch v_rate_limits and the eval trend |
| 48 | Final config and freeze (Oct 16, Rohit) | Extractor on gemini-2.5-flash (3.8 Flash took 18-28 s on video, 2.5 takes 10-13 s, and costs less); Judge limit 45 s; everything else as decision 47. Tested and reverted: web search on 2.5 Flash (per-prompt grounding billing, but it missed the "old video" fact checks the flood cases need; make accept 16/20 vs 17/20). Dropped: Flex for the eval runner (3.1 Pro took 100 s per call on Flex). Not built: a Check Grounding gate to skip the Critic; the Critic runs on every check. The gold eval moves 9 of 57 items between identical-config runs (1 item = 1.75 points), so changes were judged on make accept cases and cost, not on eval differences under 5 points. No model or pipeline changes before submission (tag `submission-freeze`) |
| 49 | Name, design and address (Oct 16, Rohit) | App name CHCKR (logo from `chckr_logo_hd_v2.png`), Bazaar Bright design, address https://chckr.web.app (Firebase Hosting site `chckr`). The old site redirects every page to the new address and keeps serving `/api`, so old result links, correction cards and audio keep working; a 301 redirect would turn the old app's POSTs into GETs. No trust seal for AGREED_BY_GROUNDING_CHECK (gate not built) |
| 50 | Evidence score, replay only (Oct 18, Rohit) | A deterministic log-odds score in `verify/source_policy.py` over the items the Judge placed for and against the claim. Weights in `config/source_tiers.yaml` `evidence_score` are **initial, to be calibrated**: support tier 1 +3.0, tier 2 +1.5, tier 3 +0.7, fact check rated true +3.0; contradict tier 1 -3.0, tier 2 -1.5, tier 3 -0.7, fact check rated false -3.5; not a source 0; repeat offenders and domains under 90 days add nothing when supporting. Items with one origin (same title, embedding similarity above 0.9, one citing the other) count once, plus 0.2 per extra item. p = 1 / (1 + exp(-score)). Cutoffs: high harm (HEALTH, GOVERNMENT_SCHEME, FINANCIAL_OFFER, EVENT about disasters, communal violence or elections) TRUE at p >= 0.95, FALSE at p <= 0.05; others 0.85 / 0.15. The score may block a TRUE or FALSE; an upgrade from NOT_ENOUGH_EVIDENCE goes to the Critic; MISLEADING and SCAM stay with the Judge. Replayed only (`scripts/replay_evidence_score.py`); live gating waits until after judging (7 Nov) |

## Link fetching: oEmbed and public metadata, what it misses (answer to question 11)

| Platform | What oEmbed or public metadata gives | What we miss |
| --- | --- | --- |
| YouTube | Title from oEmbed; Gemini reads the full public video from the URL | Private and age-restricted videos |
| X / Twitter | Post text and author handle via publish.twitter.com oEmbed, no login | Attached images and videos |
| Instagram | Since Nov 2025 Meta removed author name and thumbnail from oEmbed; caption sometimes present in embed HTML; needs a Meta app token | Reel video and audio, images, Stories, private accounts |
| Facebook | Same as Instagram | Videos, images, group posts, friends-only posts |
| LinkedIn | Open Graph description often holds the post text | Images, documents, video |
| News sites, blogs | Full article text, headline image, publish date | Paywalled text |
| Telegram public channels | Open Graph preview text and image | Videos |

The biggest gap is video inside Instagram, Facebook and X. Scraping services (Firecrawl, Apify) would close part of it, but they break Meta's terms, are not Google, and cost money. Our answer: use the ladder, and when media is missing, ask the user for a screenshot or screen recording in one tap. Note that WhatsApp forwards, the main use case, usually arrive as the media file itself, so this gap matters less than it looks.
