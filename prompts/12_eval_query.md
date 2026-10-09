version: eval-query-1.0
model: flash

Evaluation helper (not shown to users). We test whether our fact-check search finds a published fact check when the same claim reaches us in a different language, the way a forward is retold in another language. Rewrite the claim below as a person forwarding it in {{target_language_name}} ({{target_language}}) would state it, then write the search queries our intake step would write.

<user_content>
Claim, as summarised by a fact-checker in {{source_language}}: {{claim_text}}
</user_content>

Return JSON:
- claim_original: the claim in {{target_language_name}}, in its usual script, one or two sentences, faithful to the meaning. Keep names of people and places
- claim_en: one self-contained English sentence of the same claim
- search_queries_original: 2 short search queries in {{target_language_name}}
- search_queries_en: 2 short English search queries
Never add a verdict or say whether the claim is true.
