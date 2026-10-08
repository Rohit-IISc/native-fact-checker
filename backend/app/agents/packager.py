"""Evidence packager (prompts/07_packager.md): neutral per-claim briefs for the judge. Code builds the
EvidencePack around the model's briefs, so ids, tiers and URLs can never be changed by the model."""
from __future__ import annotations

import json

from app.llm import LLM, StageFailed
from app.models import (
    AgentFindings,
    ClaimBrief,
    Evidence,
    EvidencePack,
    Extraction,
    PackagerOutput,
    SourceTier,
    Stance,
)
from app.prompts import load_prompt
from app.settings import get_config

PROMPT = "07_packager.md"
_TIER_RANK = {SourceTier.TIER_1: 0, SourceTier.TIER_2: 1, SourceTier.TIER_3: 2, SourceTier.NOT_A_SOURCE: 3}


def _ranked(evidence: list[Evidence], claim_id: str) -> list[Evidence]:
    items = [e for e in evidence if e.claim_id == claim_id and e.stance != Stance.UNRELATED]
    return sorted(items, key=lambda e: (_TIER_RANK[e.tier], e.stance == Stance.CONTEXT))


def _dedupe(evidence: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    out = []
    for e in evidence:
        key = (e.claim_id, (e.url or e.evidence_id).rstrip("/").lower())
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


MEDIA_ITSELF = "media_itself"


def media_evidence(extraction: Extraction) -> list[Evidence]:
    """The extractor's neutral observations of the shared item (satire tag, masthead date, watermark), one
    item per claim. NOT_A_SOURCE and CONTEXT: they help the judge see what the item is, and the source
    policy never counts them (decisions log, Oct 8). Never the post's claim or wording."""
    markers = [m.strip()[:200] for m in extraction.media_markers if m.strip()][:5]
    if not markers:
        return []
    snippet = "Observed on the shared item itself (not a source): " + " ".join(markers)
    return [Evidence(evidence_id=f"mi-{c.claim_id}", agent=MEDIA_ITSELF, claim_id=c.claim_id,
                     publisher="The shared item itself", snippet_en=snippet, stance=Stance.CONTEXT,
                     tier=SourceTier.NOT_A_SOURCE) for c in extraction.claims]


def _with_media(ids: list[str], by_id: dict[str, Evidence], claim_id: str) -> list[str]:
    """The media observation rides on top of the item cap: it is one line and never crowds out a source."""
    mi = f"mi-{claim_id}"
    return ids if mi not in by_id or mi in ids else [*ids, mi]


def _all_evidence(extraction: Extraction, findings: list[AgentFindings]) -> list[Evidence]:
    return _dedupe([e for f in findings for e in f.evidence] + media_evidence(extraction))


def code_pack(check_id: str, extraction: Extraction, findings: list[AgentFindings], missing: list[str],
              briefs: list[ClaimBrief] | None = None) -> EvidencePack:
    max_items = int(get_config().limits["evidence"]["max_items_per_claim"])
    evidence = _all_evidence(extraction, findings)
    by_id = {e.evidence_id: e for e in evidence}
    model_briefs = {b.claim_id: b for b in briefs or []}
    out_briefs, kept_ids = [], []
    for c in extraction.claims:
        ranked = _ranked(evidence, c.claim_id)
        b = model_briefs.get(c.claim_id)
        if b:
            ids = [i for i in b.evidence_ids if i in by_id and by_id[i].claim_id == c.claim_id
                   and by_id[i].stance != Stance.UNRELATED]
            ids = list(dict.fromkeys(ids))
            ids += [e.evidence_id for e in ranked if e.evidence_id not in ids]  # never lose evidence silently
            brief = b.model_copy(update={"evidence_ids": _with_media(ids[:max_items], by_id, c.claim_id),
                                         "claim_en": c.claim_en,
                                         "claim_type": c.claim_type.value})
        else:
            brief = ClaimBrief(
                claim_id=c.claim_id, claim_en=c.claim_en, claim_type=c.claim_type.value,
                claimed_date=c.claimed_date, place=c.place,
                brief_en="No summary available; read the evidence items directly.",
                evidence_ids=_with_media([e.evidence_id for e in ranked[:max_items]], by_id, c.claim_id),
                gaps_en=[] if any(e.agent != MEDIA_ITSELF for e in ranked)
                else ["No evidence was found for this claim."],
            )
        out_briefs.append(brief)
        kept_ids += brief.evidence_ids
    sa = next((f.source_assessment for f in findings if f.source_assessment), None)
    ai = next((f.ai_generation_signals for f in findings if f.ai_generation_signals), None)
    return EvidencePack(check_id=check_id, briefs=out_briefs, evidence=[by_id[i] for i in kept_ids],
                        source_assessment=sa, ai_generation_signals=ai or extraction.ai_generation_signals,
                        missing_lanes=missing)


async def run(llm: LLM, check_id: str, extraction: Extraction, findings: list[AgentFindings], missing: list[str],
              timeout_s: float) -> EvidencePack:
    base = code_pack(check_id, extraction, findings, missing)
    if not any(e.agent != MEDIA_ITSELF for e in base.evidence):
        return base  # nothing to summarise; the judge will see the gaps
    prompt = load_prompt(PROMPT)
    payload = {
        "claims": [{"claim_id": c.claim_id, "claim_en": c.claim_en, "place": c.place,
                    "claimed_date": c.claimed_date.isoformat() if c.claimed_date else None}
                   for c in extraction.claims],
        "evidence": [e.model_dump(mode="json", exclude={"agent"}) for e in _all_evidence(extraction, findings)],
        "source_assessment": base.source_assessment.model_dump(mode="json") if base.source_assessment else None,
        "agent_notes": {f.agent: f.notes_en for f in findings if f.notes_en},
        "earliest_appearance": next((f.earliest_appearance for f in findings if f.earliest_appearance), None),
    }
    text = prompt.render(max_items=get_config().limits["evidence"]["max_items_per_claim"],
                         missing_lanes=", ".join(missing) or "none",
                         claims_and_findings_json=json.dumps(payload, ensure_ascii=False, indent=1))
    try:
        out = await llm.generate(stage="packager", prompt=text, prompt_version=prompt.version,
                                 schema=PackagerOutput, timeout_s=timeout_s)
    except StageFailed:
        return base  # degrade: the judge reads ranked evidence without briefs
    return code_pack(check_id, extraction, findings, missing, out.briefs)
