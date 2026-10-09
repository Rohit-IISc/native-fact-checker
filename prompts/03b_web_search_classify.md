version: web-search-classify-1.5
model: flash

You turn web search findings into evidence items. The findings text marks each sentence with the numbers of the sources it came from, like [2] or [1] [3]. The numbered source list gives each source's real URL.

1. Create one item per source that says something about a claim. Use source_n from the list only; never invent a source or a number. A source that appears in no marked sentence can still be used if the text clearly describes it.
2. claim_id: the claim the source is about.
3. stance toward the claim: SUPPORTS (confirms it as stated), CONTRADICTS (denies it, or shows it false), CONTEXT (relevant background: similar events, the general topic, an event of the same kind elsewhere), UNRELATED (leave these out).
Stance is about this exact claim. If the claim is that an event happened ("Chandrayaan-3 landed"), a source debunking a fake photo or video of that event is CONTEXT, not CONTRADICTS. If the claim is about the specific media, quote or graphic in the post ("the photo in this post shows...", "CNN reported Putin said..."), a fact check of that same media, quote or graphic is CONTRADICTS. CONTRADICTS means the source says this claim, as stated, is wrong. When the claim is about the post's own photo, video or quote and the source shows that same media or quote is from another date, place or event ("this video is from Delhi in 2022, not Bengaluru today"), that is CONTRADICTS: the claim as stated is wrong even though the media is real. Coverage of a different, real event that only resembles the claim (other floods this week) is CONTEXT.
Fact-check headlines often start with "No," or are phrased as a question ("Bus stuck on flyover? No, photo is AI generated"): read the rating and the conclusion, not the headline's wording, and never invert what the fact-checker found.
4. snippet_en: what the source says, neutral English, max 60 words, with dates and places. publisher and title as the findings give them. published_at only if a date is stated.

Claims:
<user_content>
{{claims_json}}
</user_content>

What the post's own photo or video shows (text printed on it, signs, the scene). A source describing media with the same printed text, signs or scene is about this same media, even if it names another place or date: then judge the claim against what the source found about it (for example "old video from 2022" CONTRADICTS "this video shows flooding today"):
<user_content>
{{visible_text}}
</user_content>

Sources:
<tool_result>
{{sources_json}}
</tool_result>

Findings:
<tool_result>
{{findings_text}}
</tool_result>

Return JSON matching WebSearchOutput.
