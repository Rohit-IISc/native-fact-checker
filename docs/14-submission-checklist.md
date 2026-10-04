# 14. Submission checklist (AI Builder Cup deck, repo, video, live link)

The template has 16 slides. Slide 2 is an instruction slide; delete it before submitting. Slides 15 and 16 are blank Google closing slides.

| Slide | Title | What goes in | Produced by |
| --- | --- | --- | --- |
| 1 | Team details | Team: Frugalists. Leader: Rohit. Problem statement title and theme (Media, Content and Digital Experiences) | Manual |
| 3 | Brief about the idea | One-line pitch from doc 01 plus the language-gap numbers from the skeleton | Manual |
| 4 | Opportunities | Differentiation table vs What The Fact, MCA deepfake tipline, newsroom tiplines, Cofacts; USP: native-language spoken verdict, cross-lingual cache, two-model review panel with mandatory credible sources, correction that travels back to the group | Skeleton + doc 16 |
| 5 | Features | Share sheet intake, 5 input types, live progress, 5-label verdict with confidence, evidence for and against, audio in 5 languages, correction card, shareable result page, history, AI-generated media assessment with both sides | Doc 01 |
| 6 | Process flow | Customer journey + app workflow (your two diagrams, updated with the cache tiers and the panel) | Your diagrams + doc 02 Mermaid |
| 7 | Wireframes (optional) | Screenshots of the 7 screens | Your call |
| 8 | Architecture diagram | GCP architecture: PWA, Cloud Run, Pub/Sub, Firestore, Vertex AI, ADK agents, TTS, Vision, Fact Check API, BigQuery | Export doc 02 Mermaid, then redraw cleanly |
| 9 | Technologies | Gemini Flash and Pro on Vertex AI, ADK, Grounding with Google Search, Gemini TTS, Gemini embeddings, Firestore vector search, Cloud Vision, Fact Check Tools API, Cloud Run, Pub/Sub, Firebase, BigQuery, Cloud Build | CLAUDE.md stack |
| 10 | Estimated cost (optional, do it) | Cost per check by lane, prototype month total, cost at 100K checks per day before and after optimizations | Doc 13 |
| 11 | Snapshots | Real screenshots: share from WhatsApp, live progress, result in Hindi, Tamil, Kannada, Indonesian, English, correction card in WhatsApp | Oct 15 |
| 12 | Performance and benchmark | Recall at 5 by language pair, verdict accuracy, abstention curve, panel agreement, p50 and p95 latency by lane, cost per check, cache hit rate | BigQuery + eval run on Oct 15 |
| 13 | Future development | Doc 01 "Later" list, cost optimizations from doc 13, revenue paths | Docs 01, 13 |
| 14 | Links | Public GitHub repo, 3-minute demo video, live product link | Oct 17 |

## Things often missed (check each)

- [ ] Benchmark numbers are real and dated, with the eval set size stated (judges weight technical merit at 40%)
- [ ] Cost slide filled even though optional
- [ ] Live link works for a judge on a laptop (no share sheet there): paste and upload work, and judge emails are on the allowlist with 50 checks per day
- [ ] Demo examples pre-cached so the first thing a judge tries is instant
- [ ] Responsible AI note: abstains when evidence is thin, two-model review, source policy, no generated imagery, media deleted in 24 hours, consent screen. Put it on slide 13 or as a line on slide 5
- [ ] Limitations stated honestly: Android-only share target, Meta links often give caption only, satellite checks limited by imagery revisit time
- [ ] Repo is public, has README with architecture diagram, setup steps, and a LICENSE (Apache 2.0 suggested); `gitleaks` clean; no API keys in history
- [ ] Repo README says which parts were built with AI coding help, if the competition rules ask for disclosure (check the FAQ)
- [ ] Demo video exactly under 3 minutes, captions on, shows a real Android phone
- [ ] Deployed on Google Cloud as the competition requires
- [ ] Deck exported to PPTX from the template, not a new design

## Demo video script (2:50)

| Time | Shot | Voiceover |
| --- | --- | --- |
| 0:00 to 0:20 | Family WhatsApp group with a Hindi flood video forward | The problem and the numbers: most Indians do not read English; fact checks take days and are mostly in English |
| 0:20 to 0:55 | Share to the app from WhatsApp, live progress screen ticking | One tap. Agents search news, fact-checkers, the image's history, and the source's record, in Hindi and English |
| 0:55 to 1:25 | Result: MISLEADING, audio plays in Hindi, sources listed | It is a 2022 video from another city; audio names the sources |
| 1:25 to 1:45 | Forward the correction card back to the group | The correction travels back to where the rumour started |
| 1:45 to 2:05 | A friend shares the same video in Kannada; answer in 3 seconds | Shared cache across languages |
| 2:05 to 2:25 | Tamil health remedy: NOT_ENOUGH_EVIDENCE, or AI image with evidence both ways | It says when it is not sure, and shows both sides |
| 2:25 to 2:50 | Architecture and benchmark slide | Gemini, ADK, review panel, recall at 5, latency, cost per check |
