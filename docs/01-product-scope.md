# 01. Product scope

## One line

Share any forward or post into the app, get back in your own language whether it is true, why, and who says so, as text and audio, with a card you can forward back to the group.

## Customer journey

1. User sees a social media post or WhatsApp forward
2. Shares it (screenshot, media file, text or link) to our PWA from the Android share sheet, or pastes/uploads inside the app
3. App verifies; a live progress screen shows each stage
4. Verdict appears on screen; if the user left, a push notification arrives
5. User reads or plays the verdict in the content's language, sees sources with links, and can forward the correction card or result link

## Inputs accepted (prototype)

| Input | Limit | Notes |
| --- | --- | --- |
| Text (forward body) | 10,000 characters | Shared via share sheet text or pasted |
| Images / screenshots | Up to 10 per share | JPEG, PNG, WEBP; HEIC converted on server |
| Video | 1 per share, up to 3 minutes | MP4, 3GP, WEBM, MOV. Longer videos: first 3 minutes checked, user told |
| Audio / voice note | 1 per share, up to 3 minutes | OPUS (WhatsApp), MP3, M4A, WAV |
| Link | 1 per share | See link fetch ladder in doc 03 |
| Total size | 50 MB per share | Rejected client side and server side |

## Claims

- One verdict per claim
- At most 3 claims checked per share (config `limits.max_claims_per_check`). Extra claims are listed as "not checked" so the user knows
- Non-checkable content returns status NOT_CHECKABLE with a type: OPINION, SATIRE, JOKE, GREETING, PROMOTION, DEVOTIONAL, PERSONAL_MESSAGE, OTHER. The answer says what it is and that there is nothing to fact-check
- If a share mixes checkable and non-checkable parts, only the checkable claims get verdicts

## Verdict scale (5 labels)

| Label | Meaning |
| --- | --- |
| TRUE | Credible sources confirm the claim as stated, including its date and place |
| FALSE | Credible sources contradict the claim |
| MISLEADING | Real content, wrong context: old photo with new caption, real event on a different date or place, edited or clipped |
| SCAM | Content designed to defraud (fake job, fake lottery, fake government scheme). No dedicated scam agent; detected from general evidence |
| NOT_ENOUGH_EVIDENCE | Evidence is thin, conflicting, or the panel split. Still shows all evidence for and against |

Each verdict has a confidence (0 to 100) and a band (LOW under 60, MEDIUM 60 to 84, HIGH 85 and above). TRUE, FALSE, MISLEADING and SCAM require the source policy to pass.

AI-generated media questions get an `ai_generation` block: likelihood 0 to 100, signals pointing to AI, signals pointing to real. The answer explains both sides, for example: "62 out of 100 likely AI-made because the hands and the shop sign text are distorted. However, the same photo appears in a 2019 news report, which points to it being real."

## Languages

- Answer language = the language of the forwarded content. Code-mixed content (Hinglish in Latin script) gets a reply in the same language and script
- English text is always shown under the native text
- Demo and test languages: Hindi (hi-IN), Tamil (ta-IN), Kannada (kn-IN), Indonesian (id-ID), English (en-IN)
- Other languages: text answer if Gemini supports them, audio only if Gemini TTS supports them, else text only
- Gemini TTS lists Tamil as GA and Kannada as Preview. If Kannada preview audio is poor in testing, fall back to Chirp 3 HD voices for kn-IN (config switch)
- UI chrome (buttons, labels) translated into the 5 demo languages; UI language follows the device, user can switch

## Output

1. Verdict screen: label, confidence, one-line summary, claim, what is actually true, evidence for and against, sources with links
2. Audio, 30 to 45 seconds, always in this order: what the post claims, the verdict, what is actually true, how sure we are, where that comes from (sources named aloud). Source links shown under the audio player
3. Correction card image (1080 x 1350) in the content language, forwardable to WhatsApp
4. Public result page `/r/{verdict_id}` with no user data, so a forwarded link opens without sign-in

## Out of scope now

Bank SMS, phishing emails, scam checker agent, human escalation, iOS share target, native apps, public API, LLM router. Satellite verifier is a stretch goal.

## Later (for the deck's future slide)

Cost (added Oct 16, after the cost review in docs/13):
- **Cascade judge:** a cheap judge (Flash) decides first and escalates to Pro only when unsure (low confidence,
  weak grounding score, or a label that always gets the full panel). Pro is about half of a full check's model cost.
- **Check Grounding gate before the Critic:** score the Judge's answer against the evidence with Vertex AI check
  grounding; skip the Critic only when every statement is well supported, confidence is high and the label is
  not SCAM. Prototyped and unit-tested on Oct 16, not shipped (the eval was too noisy to prove it safe).
- **Fewer grounded searches per check:** grounding is about half of a full check's cost (2.4-4.2 search queries,
  billed per query on Gemini 3); merge the claim's queries into fewer searches or skip web search when a
  fact check already answers the claim.
- **On-device Gemma for extraction:** run claim extraction on the phone (Gemma on Android), sending the server
  only the claims and media fingerprints. Cuts the extractor cost and keeps more of the forward on the device.

After submission (added Oct 18, Rohit):
- **Leaner, smarter agent workflow:** route each claim only to the evidence agents it needs, merge searches,
  use a cheaper first-pass judge, and route better so fewer answers end as NOT_ENOUGH_EVIDENCE when the
  evidence exists but was not found or weighed well.
- **Answers in each reader's display language:** a verdict is written in the language of the checked post,
  and every user who sees it (Recent checks, Trending, a shared link, a cache hit) gets that language. One
  user checks a Hindi video; another user who reads only Kannada sees Hindi text and audio. The verdict, claim,
  audio and all visible text should follow each reader's display language, with the original one tap away.
  This also fixes "Try an example", whose buttons follow the display language while the answer opens in the
  original post's language.
- **Localised Recent checks and Trending:** show each reader the claims checked in their language (or
  translated into it) first, so the feed is not crowded with languages they do not read.

Evidence score (added Oct 18, decision 50):
- **Independence grouping:** replace embedding similarity with shared exact sentences (long n-gram overlap)
  plus wire bylines (PTI/IANS/ANI) and identical lead paragraphs; independent newsrooms on one event score
  0.91-0.93 on embeddings, so embeddings can't separate copies from independent reporting.
- **Fit the weights by logistic regression** on the gold set plus agreed verdicts (features: tier, fact-check
  rating, direction, group size), replacing the initial hand-set weights; then turn on live gating.

Sign-in (added Oct 16, UI brief):
- **Sign in with phone number (OTP):** Firebase phone auth as a second option next to Google, for users without
  a Google account on the phone. Not built: SMS costs money per sign-in and needs abuse limits.

LLM router that picks which sub-agents to call (cost), WhatsApp bot, Android and iOS apps, B2B API for platforms, newsrooms and telcos, bank SMS and phishing checks, satellite verification, voice line for basic phones, more languages.
