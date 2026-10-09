version: eval-claim-form-1.0
model: flash

Evaluation helper (not shown to users). Fact-checkers publish a "claim" field next to their rating, but some write their conclusion or a headline there instead of the claim itself. We only keep items where the text is the claim as people circulated it, because the rating applies to that claim.

For each item decide its form:
- CLAIM: the assertion as it circulated, stated as true ("Trump said he is a big fan of Hindus", "Video shows a metro train accident at Bommanahalli")
- CONCLUSION: the fact-checker's finding or a negation of the claim ("Trump did not say ...", "AI video shared claiming ...", "Old video falsely shared as ...", "No, the government is not giving ...")
- OTHER: a question, a topic, a headline without a clear assertion, or too vague to check ("Covishield side effects?")

<user_content>
{{items_json}}
</user_content>

Return JSON: {"items": [{"id": "...", "form": "CLAIM" | "CONCLUSION" | "OTHER"}]} with one entry per input item, same ids.
