version: near-match-1.0
model: flash

Decide whether a new claim is the same claim as one we already checked, so we can reuse the earlier verdict.

SAME: same event or assertion, same place, same time frame. Different wording, language or minor detail is fine.
SAME_CLAIM_DIFFERENT_DATE: same event or assertion and place, but the new post claims a different time (for example the old one was a flood on 12 Aug 2024 and the new one says "today").
DIFFERENT: a different event, place, person, number, or a materially different assertion. "Petrol price hiked by Rs 5" and "Petrol price hiked by Rs 15" are DIFFERENT.

When unsure, answer DIFFERENT. A wrong reuse is worse than a slower check.

New claim: {{new_claim_en}}
New claimed date: {{new_claimed_date}}
Share date: {{share_date}}

Cached claim: {{cached_claim_en}}
Cached event date: {{cached_event_date}}
Cached verdict: {{cached_label}}

Return JSON: {"decision": "...", "reason": "one sentence"}
