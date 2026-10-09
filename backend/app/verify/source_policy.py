"""Source policy (docs/09), enforced in code.

TRUE, FALSE, MISLEADING or SCAM need, among the cited evidence ids:
  - at least 1 TIER_1 source, or at least 2 TIER_2 sources from different publishers, and
  - no cited id with tier NOT_A_SOURCE used as support, and
  - every cited id present in the evidence pack, and
  - at least one cited item that confirms or contradicts the claim (SUPPORTS or CONTRADICTS): background
    alone (CONTEXT) cannot carry a verdict (decision 46: old crocodile sightings read as "real event,
    wrong date" gave MISLEADING at 90% for a new sighting, case 15).
Otherwise the label becomes NOT_ENOUGH_EVIDENCE and the reason is recorded.

Items from agent "media_itself" (neutral observations of the shared item, such as a satire tag) may be
cited to explain what the item is, but are ignored when counting: they never satisfy or fail the policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models import Evidence, JudgeVerdict, Label, SourceTier, Stance
from app.verify.source_tiers import host_of

DECISIVE = {Label.TRUE, Label.FALSE, Label.MISLEADING, Label.SCAM}


@dataclass(frozen=True)
class PolicyResult:
    passed: bool
    reason: str | None = None


def _publisher_key(ev: Evidence) -> str:
    if ev.publisher:
        return ev.publisher.strip().lower()
    return host_of(ev.domain or ev.url or "") or ev.evidence_id


def check(verdict: JudgeVerdict, evidence: list[Evidence]) -> PolicyResult:
    if verdict.label not in DECISIVE:
        return PolicyResult(True)
    by_id = {e.evidence_id: e for e in evidence}
    cited_all = set(verdict.cited_ids) | set(verdict.evidence_for_ids) | set(verdict.evidence_against_ids)
    unknown = sorted(i for i in cited_all if i not in by_id)
    if unknown:
        return PolicyResult(False, f"cited ids not in evidence pack: {', '.join(unknown)}")
    cited = [by_id[i] for i in verdict.cited_ids if by_id[i].agent != "media_itself"]
    if not cited:
        return PolicyResult(False, "no cited evidence")
    social = [e.evidence_id for e in cited if e.tier == SourceTier.NOT_A_SOURCE]
    if social:
        return PolicyResult(False, f"NOT_A_SOURCE evidence used as support: {', '.join(social)}")
    if all(e.stance == Stance.CONTEXT for e in cited):
        return PolicyResult(False, "only background (CONTEXT) evidence; nothing confirms or contradicts the claim")
    if any(e.tier == SourceTier.TIER_1 for e in cited):
        return PolicyResult(True)
    tier2_publishers = {_publisher_key(e) for e in cited if e.tier == SourceTier.TIER_2}
    if len(tier2_publishers) >= 2:
        return PolicyResult(True)
    return PolicyResult(False, "needs 1 TIER_1 or 2 TIER_2 sources from different publishers")


def apply(verdict: JudgeVerdict, evidence: list[Evidence]) -> tuple[JudgeVerdict, PolicyResult]:
    """Return the verdict, downgraded to NOT_ENOUGH_EVIDENCE if the policy fails."""
    result = check(verdict, evidence)
    if result.passed:
        return verdict, result
    known = {e.evidence_id for e in evidence}
    downgraded = verdict.model_copy(update={
        "label": Label.NOT_ENOUGH_EVIDENCE,
        "confidence": min(verdict.confidence, 50),
        "cited_ids": [i for i in verdict.cited_ids if i in known],
        "evidence_for_ids": [i for i in verdict.evidence_for_ids if i in known],
        "evidence_against_ids": [i for i in verdict.evidence_against_ids if i in known],
        "reasoning_en": f"{verdict.reasoning_en}\n[Source policy: {result.reason}]",
    })
    return downgraded, result
