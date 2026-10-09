"""Second look at background evidence for claims about the post's own photo or video (prompts/14_same_media.md).

The classifiers run in parallel and sometimes file a fact check of this very video ("old 2022 Bengaluru
video falsely shared as Delhi floods") as CONTEXT, because it was written about another story. Since the
source policy no longer lets CONTEXT alone carry a verdict (decision 46), that turns a clear MISLEADING into
NOT_ENOUGH_EVIDENCE (case 01, Oct 9). One Flash call asks, per such item, whether it is about the same
media and contradicts the claim; code then sets CONTRADICTS. Only runs when it can matter.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.agents.web_search import visible_text
from app.llm import LLM, StageFailed
from app.models import AgentFindings, ClaimType, Evidence, Extraction, SourceTier, Stance
from app.prompts import load_prompt

PROMPT = "14_same_media.md"
MAX_ITEMS = 6
_MEDIA_CLAIM = re.compile(r"\b(photo|video|image|picture|clip|screenshot|graphic)s?\b[^.]{0,40}\bin this post\b",
                          re.IGNORECASE)
_AGENTS = ("factcheck_sites", "web_search", "media_provenance")


class SameMedia(BaseModel):
    evidence_id: str
    same_media: bool
    contradicts: bool
    reason_en: str = ""


class SameMediaOutput(BaseModel):
    items: list[SameMedia]


def is_media_claim(claim_type: ClaimType, claim_en: str) -> bool:
    return claim_type == ClaimType.MEDIA_AUTHENTICITY or bool(_MEDIA_CLAIM.search(claim_en))


def candidates(extraction: Extraction, findings: list[AgentFindings]) -> dict[str, list[Evidence]]:
    """claim_id -> credible CONTEXT items worth a second look (tier 1 or 2, from the search agents)."""
    if visible_text(extraction) == "none":
        return {}
    media_claims = {c.claim_id for c in extraction.claims if is_media_claim(c.claim_type, c.claim_en)}
    out: dict[str, list[Evidence]] = {}
    for f in findings:
        if f.agent not in _AGENTS:
            continue
        for e in f.evidence:
            if (e.claim_id in media_claims and e.stance == Stance.CONTEXT
                    and e.tier in (SourceTier.TIER_1, SourceTier.TIER_2)):
                out.setdefault(e.claim_id, []).append(e)
    return {k: v[:MAX_ITEMS] for k, v in out.items()}


async def run(llm: LLM, extraction: Extraction, findings: list[AgentFindings], timeout_s: float) -> list[str]:
    """Re-mark same-media items as CONTRADICTS in place. Returns the evidence ids changed. Never raises."""
    todo = candidates(extraction, findings)
    if not todo or timeout_s < 2:
        return []
    prompt = load_prompt(PROMPT)
    claims = {c.claim_id: c for c in extraction.claims}
    changed: list[str] = []
    for claim_id, items in todo.items():  # one call per media claim; posts rarely have more than one
        text = prompt.render(
            claim_en=claims[claim_id].claim_en, visible_text=visible_text(extraction),
            sources_json=json.dumps([{"evidence_id": e.evidence_id, "publisher": e.publisher, "title": e.title,
                                      "rating": e.rating_text, "says": e.snippet_en} for e in items],
                                    ensure_ascii=False, indent=1))
        try:
            out = await llm.generate(stage="same_media", prompt=text, prompt_version=prompt.version,
                                     schema=SameMediaOutput, timeout_s=timeout_s)
        except StageFailed:
            continue
        verdicts = {i.evidence_id: i for i in out.items}
        for e in items:
            v = verdicts.get(e.evidence_id)
            if v and v.same_media and v.contradicts:
                e.stance = Stance.CONTRADICTS
                changed.append(e.evidence_id)
    return changed
