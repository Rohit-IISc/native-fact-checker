# 03. Pipeline and agents

Each stage: input, output, model, prompt file, timeout. All outputs are Pydantic models in `schemas/models.py`. All agents are ADK `LlmAgent`s, composed with `SequentialAgent` and `ParallelAgent`, except stages marked "code".

## Stage 0. Intake (code)

- Verify Firebase ID token and App Check token
- Quota check (doc 08)
- Validate type and size (doc 01 limits). Store media in `gs://{project}-media/{check_id}/` (24 h lifecycle)
- Compute keys for tier 1 cache (doc 04): SHA-256 of bytes, perceptual hash for images (pHash via `imagehash`), keyframe pHashes for video (1 frame every 5 s via `ffmpeg`), normalized text hash
- Tier 1 lookup. On hit: return cached verdict (doc 04 handles new-language translation)

## Stage 1. Link fetch ladder (code)

Run only when the share contains a URL. Steps in order, stop at the first that yields usable content.

1. Normalize: strip tracking params, expand short links (max 5 redirects). SSRF guard: resolve DNS, reject private, loopback, link-local and metadata IPs at every hop; only http and https; 10 s total timeout; 5 MB max body
2. YouTube (youtube.com, youtu.be, shorts): pass the URL to Gemini directly as video file data, with an end offset of 180 s. Also get title via YouTube oEmbed
3. X / Twitter: `https://publish.twitter.com/oembed?url=...` returns the post text and author handle. Media is not returned; if the post's text refers to a photo or video, mark `media_missing: true`
4. Instagram / Facebook: Meta oEmbed (needs a Meta app token stored in Secret Manager). Since Nov 2025 Meta removed author and thumbnail fields; the embed HTML may still carry caption text. Then try Open Graph tags from the page HTML. Usually returns caption only, no video
5. Generic page (news, LinkedIn, Telegram public, blogs): fetch HTML, read Open Graph tags (`og:title`, `og:description`, `og:image`, `article:published_time`), extract main text with `trafilatura`, download `og:image` if present
6. If we got text but `media_missing` is true, or nothing usable at all: finish the check with what we have and show a prompt "We could not open the photo or video in this link. Share a screenshot or screen recording for a full check." A total fetch failure does not use up quota

Store `source_url`, `platform`, `fetched_at`, `published_at`, `author_handle` when available. The author handle feeds the source credibility agent.

## Stage 2. Information extractor (Gemini Flash, `prompts/01_extractor.md`)

- Input: all media parts (images inline, video/audio by GCS URI or YouTube URL), shared text, fetched page text, platform metadata
- Output `Extraction`: content language (BCP-47) and script; content summary in English; `checkable` flag and `non_checkable_type`; up to 3 claims, each with `claim_original` (in the content's language), `claim_en`, `claim_type` (EVENT, STATISTIC, QUOTE, HEALTH, SCIENCE, GOVERNMENT_SCHEME, FINANCIAL_OFFER, MEDIA_AUTHENTICITY, OTHER), entities, place, `claimed_date`, `time_sensitivity` (LIVE_EVENT or EVERGREEN), `search_queries_original` and `search_queries_en`; OCR text; transcript; visual description; `ai_generation_signals` (visual cues only, not a verdict)
- Video over 60 s uses low media resolution
- Timeout: 15 s + 0.2 s per media second

## Stage 3. Tier 2 cache (code + Flash)

Embed `claim_en` per claim, vector search, near-match check with `prompts/02_near_match.md`. Details in doc 04. Claims that hit are answered from cache; only the rest continue.

## Stage 4. Fan-out (ADK ParallelAgent, all Gemini Flash)

Each agent gets the `Extraction` and returns `AgentFindings`: a list of `Evidence` items (id, url, domain, title, publisher, published_at, language, snippet in English, stance SUPPORTS / CONTRADICTS / CONTEXT / UNRELATED, which claim it relates to, source tier filled by code later) plus notes.

| Agent | Prompt | Tools | Notes |
| --- | --- | --- | --- |
| Web search | `03_web_search_agent.md` | ADK built-in `google_search` (Grounding with Google Search) | Search in the original language first, then English. Max 4 grounded queries per check. Built-in google_search cannot share an agent with other tools in ADK, so this agent has only that tool |
| Fact-check sites | `04_factcheck_agent.md` | Function tools: `factcheck_text_search(query, language_code)` and `factcheck_image_search(image_uri)` calling the Fact Check Tools API (`claims:search`, `claims:imageSearch`) | Query in original language, English, and Hindi if content is in another Indian language. Returns ClaimReview ratings with publisher and URL |
| Source credibility | `05_source_credibility_agent.md` | Function tools: `lookup_source(domain_or_handle)` reading Firestore `sources`, `domain_info(domain)` (domain age via RDAP) | Rates the origin of the post (account, domain, outlet). Verification badges are treated as near-zero signal |
| Media provenance | `06_media_provenance_agent.md` | Function tool: `vision_web_detection(image_uri)` (Cloud Vision); keyframes for video | Finds earliest appearances of the image or keyframes: the core of the "old war or riot photo with new caption" case. Also reports AI-generation signals with reasons both ways. Skipped for text-only shares |

Agent timeout 28 s each. Code assigns the source tier to every Evidence item from `config/source_tiers.yaml` and the `sources` collection. Social media URLs get tier `NOT_A_SOURCE`.

## Stage 5. Evidence packager (Gemini Flash, `prompts/07_packager.md`)

Dedupes evidence, drops UNRELATED, keeps at most 12 items per claim ranked by tier then relevance, writes a neutral English brief per claim: what is claimed, what each source says, dates and places, what is missing. Output `EvidencePack`. The packager never gives a verdict.

## Stage 6. Review panel

1. Judge (Gemini Pro, `prompts/08_judge.md`): reads only the EvidencePack. Outputs per claim `JudgeVerdict`: label, confidence, `what_is_true`, evidence ids for and against, reasoning, `ai_generation` block when relevant. Must cite evidence ids
2. Source policy (code, `verify/source_policy.py`): for TRUE, FALSE, MISLEADING or SCAM require at least 1 TIER_1 source, or at least 2 TIER_2 sources from different publishers, among the cited ids, and no cited id with tier NOT_A_SOURCE used as support. All cited ids must exist in the pack. If the rule fails, the label becomes NOT_ENOUGH_EVIDENCE and the reason is recorded
3. Critic (Gemini Pro, `prompts/09_critic.md`): reads the EvidencePack and the Judge's output. Checks for misread dates or places, overreach beyond evidence, ignored contradicting evidence, wrong use of MISLEADING vs FALSE. Returns AGREE or DISAGREE, its own proposed label and confidence, and specific objections
4. If DISAGREE: Judge revision (Pro, `08_judge.md` in revision mode with the Critic's objections). If the revised label equals the Critic's proposed label, use it. Otherwise final label = NOT_ENOUGH_EVIDENCE, and the answer presents both readings and all evidence for and against
5. Final confidence = min(judge confidence, critic confidence) when they agree

Record `panel_outcome`: AGREED, AGREED_AFTER_REVISION, SPLIT, POLICY_DOWNGRADE.

## Stage 7. Answer composer (Gemini Flash, `prompts/10_composer.md`)

Writes in the content language and in English: headline (max 12 words), one-line summary, what the post claims, what is true, evidence for and against in plain words, and the audio script (75 to 110 words, about 30 to 45 seconds) in the fixed order. Source names spoken naturally ("according to Reuters and the Press Information Bureau"). No URLs in the audio script.

## Stage 8. Outputs (code)

- TTS: Gemini TTS with style prompt `prompts/11_tts_style.md`, voice per language from `config/languages.yaml`, MP3 to `gs://{project}-outputs/audio/{verdict_id}_{lang}.mp3`
- Correction card: Pillow built with libraqm (complex script shaping) and Noto Sans Devanagari, Tamil, Kannada and Latin fonts. Verdict color band, label in content language, the claim (trimmed), what is true, top 2 source names, short result URL. No generated imagery. Test Hindi and Kannada rendering on day one
- Write `verdicts/{verdict_id}`, cache docs, `checks/{check_id}` final state, user history, BigQuery rows
- FCM push to the user's tokens

## Model use summary

| Stage | Model key in config/models.yaml |
| --- | --- |
| Extractor, near-match, sub-agents, packager, composer | `flash` |
| Judge, Critic, revision | `pro` |
| Fallback when Pro times out | `flash` |
| Embeddings | `embedding` (768 dims) |
| TTS | `tts` |
