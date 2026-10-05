"""Review panel merge logic (docs/03 stage 6), pure code so it is unit-testable.

1. Judge verdict -> source policy (may downgrade to NOT_ENOUGH_EVIDENCE)
2. Critic AGREE -> final; confidence = min(judge, critic)
3. Critic DISAGREE -> judge revision; if revised label == critic's proposed label, use it
   (AGREED_AFTER_REVISION), else NOT_ENOUGH_EVIDENCE with both readings (SPLIT)
The revised verdict also goes through the source policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models import CriticReview, Evidence, JudgeVerdict, Label, PanelOutcome
from app.verify import source_policy


@dataclass
class PanelDecision:
    verdict: JudgeVerdict
    outcome: PanelOutcome
    policy_reason: str | None = None
    split_readings: list[str] | None = None


def after_policy(verdict: JudgeVerdict, evidence: list[Evidence]) -> tuple[JudgeVerdict, str | None]:
    v, result = source_policy.apply(verdict, evidence)
    return v, None if result.passed else result.reason


NEE_MAX_CONFIDENCE = 50


def merge(
    judge: JudgeVerdict,
    critic: CriticReview | None,
    evidence: list[Evidence],
    revised: JudgeVerdict | None = None,
) -> PanelDecision:
    """Merge one claim's panel outputs; NOT_ENOUGH_EVIDENCE never shows a HIGH confidence band."""
    d = _merge(judge, critic, evidence, revised)
    if d.verdict.label == Label.NOT_ENOUGH_EVIDENCE and d.verdict.confidence > NEE_MAX_CONFIDENCE:
        d.verdict = d.verdict.model_copy(update={"confidence": NEE_MAX_CONFIDENCE})
    return d


def _merge(
    judge: JudgeVerdict,
    critic: CriticReview | None,
    evidence: list[Evidence],
    revised: JudgeVerdict | None = None,
) -> PanelDecision:
    """Merge one claim's panel outputs. `revised` is required when the critic disagreed.

    critic=None means the critic stage failed or timed out: keep the policy-checked judge verdict
    but cap confidence so it never shows HIGH without a second opinion.
    """
    judged, reason = after_policy(judge, evidence)
    if reason:
        # A policy downgrade is final; the critic cannot upgrade past the source floor.
        return PanelDecision(judged, PanelOutcome.POLICY_DOWNGRADE, policy_reason=reason)

    if critic is None:
        capped = judged.model_copy(update={"confidence": min(judged.confidence, 84)})
        return PanelDecision(capped, PanelOutcome.AGREED)

    if critic.decision == "AGREE" and critic.proposed_label == judged.label:
        final = judged.model_copy(update={"confidence": min(judged.confidence, critic.proposed_confidence)})
        return PanelDecision(final, PanelOutcome.AGREED)

    if revised is None:
        raise ValueError("critic disagreed; a revised judge verdict is required")

    revised_checked, revised_reason = after_policy(revised, evidence)
    if revised_reason is None and revised_checked.label == critic.proposed_label:
        final = revised_checked.model_copy(
            update={"confidence": min(revised_checked.confidence, critic.proposed_confidence)}
        )
        return PanelDecision(final, PanelOutcome.AGREED_AFTER_REVISION)

    readings = [
        f"Judge: {revised.label.value} ({revised.confidence}). {revised.reasoning_en}",
        f"Critic: {critic.proposed_label.value} ({critic.proposed_confidence}). "
        + " ".join(critic.objections_en),
    ]
    for_ids = _union(judge.evidence_for_ids, revised.evidence_for_ids)
    against_ids = _union(judge.evidence_against_ids, revised.evidence_against_ids)
    known = {e.evidence_id for e in evidence}
    split = revised.model_copy(update={
        "label": Label.NOT_ENOUGH_EVIDENCE,
        "confidence": min(revised.confidence, critic.proposed_confidence, 50),
        "evidence_for_ids": [i for i in for_ids if i in known],
        "evidence_against_ids": [i for i in against_ids if i in known],
        "cited_ids": [i for i in _union(revised.cited_ids, for_ids, against_ids) if i in known],
    })
    return PanelDecision(split, PanelOutcome.SPLIT, policy_reason=revised_reason, split_readings=readings)


def _union(*lists: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for lst in lists:
        for i in lst:
            seen.setdefault(i, None)
    return list(seen)
