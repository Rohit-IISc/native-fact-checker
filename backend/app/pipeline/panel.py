"""Review panel merge logic (docs/03 stage 6), pure code so it is unit-testable.

1. Judge verdict -> source policy (may downgrade to NOT_ENOUGH_EVIDENCE)
2. Critic AGREE -> final; confidence = min(judge, critic)
3. Critic DISAGREE -> judge revision; if revised label == critic's proposed label, use it
   (AGREED_AFTER_REVISION), else NOT_ENOUGH_EVIDENCE with both readings (SPLIT)
The revised verdict also goes through the source policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models import CriticReview, Evidence, JudgeVerdict, Label, PanelOutcome, Stance
from app.verify import source_policy


@dataclass
class PanelDecision:
    verdict: JudgeVerdict
    outcome: PanelOutcome
    policy_reason: str | None = None
    split_readings: list[str] | None = None
    evidence_score: dict | None = None   # {score, reports, against}, only where the score was used (decision 50)


# Which stances may back each decisive label. CONTEXT can back any (an old photo's real origin is CONTEXT
# that makes a claim MISLEADING); the opposite stance cannot.
_BACKING = {Label.TRUE: {Stance.SUPPORTS, Stance.CONTEXT},
            Label.FALSE: {Stance.CONTRADICTS, Stance.CONTEXT},
            Label.MISLEADING: {Stance.CONTRADICTS, Stance.CONTEXT},
            Label.SCAM: {Stance.CONTRADICTS, Stance.CONTEXT}}


def reconcile_stances(verdict: JudgeVerdict, evidence: list[Evidence]) -> JudgeVerdict:
    """Make the judge's for/against lists agree with each item's classified stance, and drop cited items
    whose stance points the other way from the label, before the source policy counts sources.

    Seen Oct 5: a BOOM fact check of a fake landing photo was classified CONTRADICTS for "Chandrayaan-3
    landed" and the judge listed it as supporting evidence. Either way, an item cannot be both."""
    by_id = {e.evidence_id: e for e in evidence}
    stance = {i: by_id[i].stance for i in by_id}
    for_ids = [i for i in verdict.evidence_for_ids if stance.get(i) != Stance.CONTRADICTS]
    against_ids = [i for i in verdict.evidence_against_ids if stance.get(i) != Stance.SUPPORTS]
    for_ids += [i for i in verdict.evidence_against_ids if stance.get(i) == Stance.SUPPORTS and i not in for_ids]
    against_ids += [i for i in verdict.evidence_for_ids if stance.get(i) == Stance.CONTRADICTS
                    and i not in against_ids]
    cited, dropped = verdict.cited_ids, []
    if verdict.label in _BACKING:
        ok = _BACKING[verdict.label]
        cited = [i for i in verdict.cited_ids if i not in stance or stance[i] in ok]
        dropped = [i for i in verdict.cited_ids if i in stance and stance[i] not in ok]
    moved = (set(for_ids) ^ set(verdict.evidence_for_ids)) | (set(against_ids) ^ set(verdict.evidence_against_ids))
    if not moved and not dropped:
        return verdict
    note = []
    if moved:
        note.append(f"moved {', '.join(sorted(moved))} to match their stance")
    if dropped:
        note.append(f"{', '.join(dropped)} cannot back {verdict.label.value} (stance points the other way)")
    return verdict.model_copy(update={
        "evidence_for_ids": for_ids, "evidence_against_ids": against_ids, "cited_ids": cited,
        "reasoning_en": f"{verdict.reasoning_en}\n[Stance check: {'; '.join(note)}]",
    })


def after_policy(verdict: JudgeVerdict, evidence: list[Evidence]) -> tuple[JudgeVerdict, str | None]:
    v, result = source_policy.apply(reconcile_stances(verdict, evidence), evidence)
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
    if d.verdict.ai_generation is None and judge.ai_generation is not None:
        # A revision that omits the AI-generation assessment must not erase the judge's.
        d.verdict = d.verdict.model_copy(update={"ai_generation": judge.ai_generation})
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
