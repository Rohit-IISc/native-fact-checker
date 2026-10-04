# 09. Source credibility and source policy

Two separate things:
1. The source policy decides which evidence can back a verdict
2. The source credibility agent rates where the shared post came from

## Source tiers (for evidence)

Defined in `config/source_tiers.yaml`, assigned by code, never by the model.

| Tier | Examples | Can back a verdict? |
| --- | --- | --- |
| TIER_1 | Government and official bodies (`.gov.in`, `.nic.in`, `.go.id`, PIB Fact Check, RBI, ECI, IMD, WHO), wire agencies (Reuters, AP, AFP, PTI), IFCN signatory fact-checkers (BOOM, Alt News, Factly, Newschecker, Vishvas News, India Today Fact Check, Fact Crescendo, Mafindo, Tempo Cek Fakta and others) | Yes, 1 is enough |
| TIER_2 | Major national and international news outlets (The Hindu, Indian Express, Hindustan Times, NDTV, BBC, The New York Times, The Guardian, Kompas, Deccan Herald, Prajavani and others) | Yes, 2 from different publishers |
| TIER_3 | Other news sites, regional outlets not yet listed, blogs of known organizations | Context only |
| NOT_A_SOURCE | X, Twitter, Facebook, Instagram, Reddit, YouTube (non-official channels), Telegram, ShareChat, Moj, Quora, Medium, Blogspot, WhatsApp | Never |

Rules:
- TRUE, FALSE, MISLEADING, SCAM need at least 1 TIER_1 or at least 2 TIER_2 from different publishers among the cited evidence
- An official account's post (for example a verified government handle) is still NOT_A_SOURCE as a URL. The agent should find the same statement on the official website or a wire report
- The Judge may still rate a TIER_1 source as wrong when other TIER_1 sources contradict it. The policy sets a floor; the panel still judges
- IFCN signatory status changes. Before Oct 11, verify the fact-checker list against the IFCN signatories page and update the YAML

## Source credibility agent (for the post's origin)

Signals, in order of weight:
1. Repeat-offender record from the `sources` collection: how many times this domain or handle appeared as the claimant or appearance URL in published fact checks rated false or misleading
2. Domain age from RDAP (a news site registered 3 weeks ago is a red flag)
3. Lookalike domains (`ndtv-news.co`, `reuters-india.info`) by edit distance to tier 1 and tier 2 domains
4. Whether the outlet is in the tier list
5. Verification badges: near-zero weight, as agreed, because anyone can buy them on X and Instagram

The agent outputs a `SourceAssessment`: origin type (KNOWN_OUTLET, UNKNOWN_SITE, SOCIAL_ACCOUNT, UNKNOWN), repeat-offender count with examples, red flags, and a short note. It never decides the verdict; it is one input to the Judge.

## Building the offender list (no manual curation, no partisan labels)

We do not hand-pick "bad" sites. The list is derived from what fact-checkers have already published, which keeps it neutral and defensible.

- Seed job `scripts/seed_sources.py`: query the Fact Check Tools API across a broad topic list (elections, health, floods, riots, war, schemes, celebrities, communal, finance) in hi, ta, kn, id, en and other Indian languages, page through results, and for every ClaimReview with a false or misleading rating record the `claimant` and any appearance URLs' domains and handles. Increment counts in `sources`
- Rating text varies by publisher ("False", "Fake", "Misleading", "झूठ", "Salah", "Hoaks"). Normalize with a small mapping table in the seed script plus a Flash fallback for unknown ratings
- Auto-update: a weekly Cloud Scheduler job reruns the harvest for the past 7 days. Our own verdicts add to counts only when the panel AGREED, the label is FALSE or MISLEADING, and at least one TIER_1 source backs it (origin `OWN_VERDICTS`, kept separate so it can be audited)
- A source is flagged as a repeat offender at 3 or more false or misleading ratings, with the last 3 examples stored for the agent to cite
