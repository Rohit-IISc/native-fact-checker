version: same-media-1.0
model: flash

A post makes a claim about its own photo or video. Our search found sources that were filed as background because they seem to be about another story. Decide, for each source, whether it is actually about this same photo or video, and if so whether what it found contradicts the claim.

Same media means the source describes media with the same printed text, the same signs or logos, the same scene and action (for example "a video of a flooded road with 'DELHI संकट मे' written on it, BMRCL boards visible"). A source about another photo or video of a similar event is not the same media, even in the same city or week.

If it is the same media, contradicts is true when the source shows the claim about it is wrong: the media is older than the claim says, from another place, of another event, edited, or AI-made. If the source confirms the claim, contradicts is false.

The post's claim:
<user_content>
{{claim_en}}
</user_content>

What the post's photo or video shows:
<user_content>
{{visible_text}}
</user_content>

Sources:
<evidence>
{{sources_json}}
</evidence>

Return JSON: {"items": [{"evidence_id": "...", "same_media": true|false, "contradicts": true|false, "reason_en": "one short sentence"}]}, one entry per source.
