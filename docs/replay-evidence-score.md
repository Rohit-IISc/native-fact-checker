# Evidence score replay (Oct 18, decision 50)

Replay only: the score was recomputed on stored evidence with `scripts/replay_evidence_score.py`. No LLM
calls (embeddings only, for grouping). Live gating stays off until after judging (7 Nov). Weights are the
initial ones in `config/source_tiers.yaml` (`evidence_score`), to be calibrated.

Data: production verdicts (31 scored), dev verdicts (6), and every saved acceptance run (733 claim results,
571 main claims with an expected label). The 57-item eval gold set keeps no evidence (it runs on an
in-memory store), so it cannot be replayed without new model calls; the acceptance cases are the gold set
with stored evidence.

## Findings

1. **Final configuration (Oct 16 runs, 72 gold main claims): no TRUE or FALSE would be blocked.** Three
   NOT_ENOUGH_EVIDENCE answers would go to the Critic: Chandrayaan (gold TRUE, proposed TRUE, a fix), a news
   link (gold TRUE, proposed FALSE) and 01b (gold MISLEADING, proposed FALSE). The Critic must reject the
   last two. Production: 5 NOT_ENOUGH_EVIDENCE verdicts would go to the Critic (4 TRUE, 1 FALSE).
2. **All runs since Oct 5: 22 TRUE/FALSE blocked, 17 of them correct.** 14 are Chandrayaan runs from Oct 7-8
   (older prompts), where the Judge placed a BOOM fact check of a *different* claim ("China landed first",
   rated false) against the claim; the "rated false" weight (-3.5) then outweighed four tier 2 reports.
   A ClaimReview rating applies to the claim that was reviewed, which is not always ours.
3. **Grouping by embedding similarity above 0.9 merges independent outlets.** With Gemini embeddings,
   different articles about one event (PBS, The Guardian, VOA, Wikipedia on the moon landing) score above
   0.9, so they count as one origin. Raising the threshold to 0.95 or 0.97 changed little on the final runs
   (results below), but the merge is visible in individual verdicts (Mahadevan: The Print merged with two
   syndicated copies).
4. Changes against a wrong gold answer: on the final configuration, 1 would be fixed (if the Critic agrees)
   and 2 proposals would be wrong if accepted. Not zero, so no live gating; it waits for calibration.

Suggested before gating: apply the fact-check rating weight only when the reviewed claim matches ours (the
Judge already decides same-claim matching; record it per item), group by wire attribution and shared
sentences rather than embeddings of title plus snippet, and fit the weights (docs/01 Later).

## Mahadevan restaurant (production verdict 01M53YRTSBQ58WSB4CS4XH32J4)

Claim: "Shankar Mahadevan opened a new South Indian restaurant named Malgudi in Rajouri Garden." EVENT, not
high harm (no disaster, communal or election terms), so the cutoffs are 0.85 / 0.15. Today:
NOT_ENOUGH_EVIDENCE after a policy downgrade (needs 1 tier 1 or 2 tier 2).

| Item | Tier | Direction | Weight |
|---|---|---|---|
| Hindustan Times review | TIER_2 | supports | +1.5 |
| The Print | TIER_3 | supports | +0.7 |
| Business Today | TIER_3 | supports | +0.7 |
| Big News Network (same headline as Business Today) | TIER_3 | supports | grouped |

Groups: {Hindustan Times}, {The Print, Business Today, Big News Network} -> 1.5 + (0.7 + 0.2 x 2) = 2.6;
p = 1 / (1 + e^-2.6) = 0.93 >= 0.85, so the score proposes TRUE and the verdict would go to the Critic. If The
Print were counted as independent (it is a different article), the score would be 3.1, p = 0.96.

## Sensitivity: final-configuration runs at three thresholds

### same_origin_similarity 0.9

```
same_origin_similarity 0.9, runs accept-20261016-*

Scored 123 verdicts: firestore:(default) 31, firestore:dev-db 6, accept 86

| source | action | proposed | count |
|---|---|---|---|
| accept | kept |  | 34 |
| accept | to_critic | FALSE | 2 |
| accept | to_critic | TRUE | 1 |
| accept | unchanged |  | 49 |
| firestore | kept |  | 13 |
| firestore | to_critic | FALSE | 1 |
| firestore | to_critic | TRUE | 4 |
| firestore | unchanged |  | 19 |

Gold (acceptance runs with expected labels): 72 main claims
- currently wrong against gold: 12
- blocked TRUE/FALSE that were wrong (good): 0; that were right (bad): 0
- NEE sent to Critic where the proposal matches gold: 1; where it does not: 2
```

### same_origin_similarity 0.95

```
same_origin_similarity 0.95, runs accept-20261016-*

Scored 123 verdicts: firestore:(default) 31, firestore:dev-db 6, accept 86

| source | action | proposed | count |
|---|---|---|---|
| accept | kept |  | 34 |
| accept | to_critic | FALSE | 3 |
| accept | to_critic | TRUE | 1 |
| accept | unchanged |  | 48 |
| firestore | kept |  | 13 |
| firestore | to_critic | FALSE | 1 |
| firestore | to_critic | TRUE | 4 |
| firestore | unchanged |  | 19 |

Gold (acceptance runs with expected labels): 72 main claims
- currently wrong against gold: 12
- blocked TRUE/FALSE that were wrong (good): 0; that were right (bad): 0
- NEE sent to Critic where the proposal matches gold: 1; where it does not: 2
```

### same_origin_similarity 0.97

```
same_origin_similarity 0.97, runs accept-20261016-*

Scored 123 verdicts: firestore:(default) 31, firestore:dev-db 6, accept 86

| source | action | proposed | count |
|---|---|---|---|
| accept | kept |  | 34 |
| accept | to_critic | FALSE | 3 |
| accept | to_critic | TRUE | 1 |
| accept | unchanged |  | 48 |
| firestore | kept |  | 13 |
| firestore | to_critic | FALSE | 2 |
| firestore | to_critic | TRUE | 5 |
| firestore | unchanged |  | 17 |

Gold (acceptance runs with expected labels): 72 main claims
- currently wrong against gold: 12
- blocked TRUE/FALSE that were wrong (good): 0; that were right (bad): 0
- NEE sent to Critic where the proposal matches gold: 1; where it does not: 2
```

## All runs (same_origin_similarity 0.9)

Scored 770 verdicts: firestore:(default) 31, firestore:dev-db 6, accept 733

| source | action | proposed | count |
|---|---|---|---|
| accept | blocked |  | 22 |
| accept | kept |  | 251 |
| accept | to_critic | FALSE | 50 |
| accept | to_critic | TRUE | 19 |
| accept | unchanged |  | 391 |
| firestore | kept |  | 13 |
| firestore | to_critic | FALSE | 1 |
| firestore | to_critic | TRUE | 4 |
| firestore | unchanged |  | 19 |

Gold (acceptance runs with expected labels): 571 main claims
- currently wrong against gold: 164
- blocked TRUE/FALSE that were wrong (good): 1; that were right (bad): 17
- NEE sent to Critic where the proposal matches gold: 13; where it does not: 21

Every change against gold:

| run | judge label | expected | score | p(true) | action | proposed |
|---|---|---|---|---|---|---|
| accept-20261005-172813/20261005-173046-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.1 | 0.891 | to_critic | TRUE |
| accept-20261005-172813/20261005-173100-15-kn-thin-local-claim.json | NOT_ENOUGH_EVIDENCE | NOT_ENOUGH_EVIDENCE | 3.3 | 0.964 | to_critic | TRUE |
| accept-20261005-174440/20261005-174539-15-kn-thin-local-claim.json | NOT_ENOUGH_EVIDENCE | NOT_ENOUGH_EVIDENCE | -4.6 | 0.01 | to_critic | FALSE |
| accept-20261005-180739/20261005-180953-15-kn-thin-local-claim.json | NOT_ENOUGH_EVIDENCE | NOT_ENOUGH_EVIDENCE | -3.4 | 0.032 | to_critic | FALSE |
| accept-20261007-170226/20261007-170716-10b-en-modi-shah-old-photo-ai.json | NOT_ENOUGH_EVIDENCE | FALSE | -3.8 | 0.022 | to_critic | FALSE |
| accept-20261007-170226/20261007-170823-15-kn-thin-local-claim.json | NOT_ENOUGH_EVIDENCE | NOT_ENOUGH_EVIDENCE | -1.9 | 0.13 | to_critic | FALSE |
| accept-20261007-170950/20261007-171310-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.2 | 0.231 | blocked |  |
| accept-20261007-170950/20261007-171507-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.8 | 0.943 | to_critic | TRUE |
| accept-20261007-172108/20261007-172206-10a-en-mumbai-flyover-bus-ai.json | NOT_ENOUGH_EVIDENCE | FALSE | -2.9 | 0.052 | to_critic | FALSE |
| accept-20261007-173032/20261007-173151-10b-en-modi-shah-old-photo-ai.json | NOT_ENOUGH_EVIDENCE | FALSE | -3.2 | 0.039 | to_critic | FALSE |
| accept-20261007-173319/20261007-173612-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.0 | 0.269 | blocked |  |
| accept-20261007-183827/20261007-184254-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.0 | 0.269 | blocked |  |
| accept-20261007-183827/20261007-184552-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 3.2 | 0.961 | to_critic | TRUE |
| accept-20261007-183827/20261007-184556-02-kn-flood-reshare-720p.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -2.8 | 0.057 | to_critic | FALSE |
| accept-20261007-183827/20261007-184611-03-hi-flood-new-language.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -2.8 | 0.057 | to_critic | FALSE |
| rep1/20261008-060123-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.4 | 0.198 | blocked |  |
| rep1/20261008-060432-12-hi-nbt-holi-satire.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -2.9 | 0.052 | to_critic | FALSE |
| rep1/20261008-060549-16-en-x-quote-tweet.json | NOT_ENOUGH_EVIDENCE | NOT_CHECKABLE/NOT_ENOUGH_EVIDENCE | 2.3 | 0.909 | to_critic | TRUE |
| rep2/20261008-060946-08-en-chandrayaan3-landing.json | TRUE | TRUE | 0.1 | 0.525 | blocked |  |
| rep2/20261008-061303-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | -3.5 | 0.029 | to_critic | FALSE |
| accept-20261008-061551/20261008-062453-02-kn-flood-reshare-720p.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.7 | 0.024 | to_critic | FALSE |
| accept-20261008-061551/20261008-062458-03-hi-flood-new-language.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.7 | 0.024 | to_critic | FALSE |
| rep2/20261008-063418-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.5 | 0.924 | to_critic | TRUE |
| accept-20261008-175706/20261008-175851-01b-hi-flood-x-screenshot.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.5 | 0.029 | to_critic | FALSE |
| accept-20261008-175706/20261008-180212-08-en-chandrayaan3-landing.json | TRUE | TRUE | -0.1 | 0.475 | blocked |  |
| accept-20261008-175706/20261008-180518-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.2 | 0.9 | to_critic | TRUE |
| accept-20261009-084911/20261009-085343-08-en-chandrayaan3-landing.json | TRUE | TRUE | 0.3 | 0.574 | blocked |  |
| accept-20261009-084911/20261009-085726-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.7 | 0.937 | to_critic | TRUE |
| accept-20261009-093239/20261009-095103-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 1.9 | 0.87 | to_critic | TRUE |
| accept-20261009-095544/20261009-095742-01b-hi-flood-x-screenshot.json | FALSE | MISLEADING | 0.2 | 0.55 | blocked |  |
| accept-20261009-095544/20261009-100227-08-en-chandrayaan3-landing.json | TRUE | TRUE | 0.1 | 0.525 | blocked |  |
| accept-20261009-095544/20261009-100623-12-hi-nbt-holi-satire.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -2.1 | 0.109 | to_critic | FALSE |
| accept-20261009-095544/20261009-100803-14-en-putin-cnn-morphed.json | FALSE | FALSE | 0.0 | 0.5 | blocked |  |
| accept-20261009-101930/20261009-102615-08-en-chandrayaan3-landing.json | TRUE | TRUE | -0.2 | 0.45 | blocked |  |
| accept-20261009-101930/20261009-103055-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.6 | 0.931 | to_critic | TRUE |
| accept-20261009-105625/20261009-110227-08-en-chandrayaan3-landing.json | TRUE | TRUE | -0.4 | 0.401 | blocked |  |
| accept-20261009-112813/20261009-113014-01-kn-bengaluru-flood-video.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.9 | 0.02 | to_critic | FALSE |
| accept-20261009-112813/20261009-114044-08-en-chandrayaan3-landing.json | TRUE | TRUE | 0.7 | 0.668 | blocked |  |
| accept-20261009-112813/20261009-114634-12-hi-nbt-holi-satire.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -4.0 | 0.018 | to_critic | FALSE |
| accept-20261009-112813/20261009-114743-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | 2.5 | 0.924 | to_critic | TRUE |
| accept-20261009-112813/20261009-115112-02-kn-flood-reshare-720p.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.9 | 0.02 | to_critic | FALSE |
| accept-20261009-112813/20261009-115117-03-hi-flood-new-language.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -3.9 | 0.02 | to_critic | FALSE |
| accept-20261009-115530/20261009-120548-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.0 | 0.269 | blocked |  |
| accept-20261009-115530/20261009-121354-13-en-news-link.json | TRUE | TRUE | -1.8 | 0.142 | blocked |  |
| accept-20261009-115530/20261009-121741-02-kn-flood-reshare-720p.json | NOT_ENOUGH_EVIDENCE | MISLEADING | 2.0 | 0.881 | to_critic | TRUE |
| accept-20261009-115530/20261009-121746-03-hi-flood-new-language.json | NOT_ENOUGH_EVIDENCE | MISLEADING | 2.0 | 0.881 | to_critic | TRUE |
| accept-20261009-123824/20261009-123931-08-en-chandrayaan3-landing.json | TRUE | TRUE | -1.2 | 0.231 | blocked |  |
| accept-20261009-143456/20261009-144722-08-en-chandrayaan3-landing.json | TRUE | TRUE | -4.6 | 0.01 | blocked |  |
| accept-20261009-143456/20261009-145523-13-en-news-link.json | TRUE | TRUE | 0.3 | 0.574 | blocked |  |
| accept-20261016-160339/20261016-160915-08-en-chandrayaan3-landing.json | NOT_ENOUGH_EVIDENCE | TRUE | 7.9 | 1.0 | to_critic | TRUE |
| accept-20261016-163410/20261016-164239-13-en-news-link.json | NOT_ENOUGH_EVIDENCE | TRUE | -3.0 | 0.047 | to_critic | FALSE |
| accept-20261016-200129/20261016-200259-01b-hi-flood-x-screenshot.json | NOT_ENOUGH_EVIDENCE | MISLEADING | -4.6 | 0.01 | to_critic | FALSE |

Production and dev verdicts that would change:

| verdict | label | claim | score | p(true) | action | proposed |
|---|---|---|---|---|---|---|
| 01M46N4KRT | NOT_ENOUGH_EVIDENCE | Many Indian people's plans for Financial Independence, Retire Early (F | 3.3 | 0.964 | to_critic | TRUE |
| 01M4BSP9ZM | NOT_ENOUGH_EVIDENCE | There are 78 places where one can launch a startup for free. | 2.3 | 0.909 | to_critic | TRUE |
| 01M4G0XW92 | NOT_ENOUGH_EVIDENCE | The final date for birth registration is April 27, 2026, and this dead | -3.5 | 0.029 | to_critic | FALSE |
| 01M4GYFYNC | NOT_ENOUGH_EVIDENCE | The graphic in this post is a genuine ABP Live news report stating tha | 1.9 | 0.87 | to_critic | TRUE |
| 01M53YRTSB | NOT_ENOUGH_EVIDENCE | Shankar Mahadevan opened a new South Indian restaurant named Malgudi i | 2.6 | 0.931 | to_critic | TRUE |

