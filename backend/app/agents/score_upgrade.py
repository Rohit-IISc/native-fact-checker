"""Evidence-score upgrade (decision 50, upgrade-only): NOT_ENOUGH_EVIDENCE -> TRUE, decided by the Critic.

Runs only for a claim the panel left at NOT_ENOUGH_EVIDENCE without a split. The deterministic score
(verify/source_policy.evidence_score) must clear the harm cutoff with at least two independent supporting
origin groups and no tier 1 or tier 2 contradiction; then one Critic call (prompts/15_score_upgrade.md)
checks that the kept reports are about this exact claim and independent. The upgraded verdict still has to
pass the source policy, or it stays NOT_ENOUGH_EVIDENCE. Never raises; never touches any other label.
"""
from __future__ import annotations

import json
import logging

from app.llm import LLM, StageFailed
from app.models import Claim, Evidence, JudgeVerdict, Label, PanelOutcome, ScoreUpgradeReview
from app.observability.logging import log_event
from app.prompts import load_prompt
from app.verify import source_policy

PROMPT = "15_score_upgrade.md"
log = logging.getLogger(__name__)


def _items(ids: list[str], by_id: dict[str, Evidence]) -> str:
    return json.dumps([{"id": i, "publisher": by_id[i].publisher or by_id[i].domain, "tier": by_id[i].tier.value,
                        "title": by_id[i].title, "date": by_id[i].published_at.isoformat()
                        if by_id[i].published_at else None, "says": by_id[i].snippet_en}
                       for i in ids if i in by_id], ensure_ascii=False, indent=1)


async def run(llm: LLM, claim: Claim, verdict: JudgeVerdict, outcome: PanelOutcome, evidence: list[Evidence],
              timeout_s: float) -> tuple[JudgeVerdict, source_policy.EvidenceScore] | None:
    """The upgraded TRUE verdict and its score, or None (no upgrade)."""
    if verdict.label != Label.NOT_ENOUGH_EVIDENCE or outcome == PanelOutcome.SPLIT or timeout_s < 4:
        return None

    async def embed(texts: list[str]) -> list[list[float]]:
        return await llm.embed(texts, timeout_s=min(6.0, timeout_s / 3))

    s = await source_policy.evidence_score(verdict, evidence, claim_type=claim.claim_type, claim_en=claim.claim_en,
                                           embed=embed)
    if source_policy.gate(verdict.label, s).action != "to_critic":
        return None
    by_id = {e.evidence_id: e for e in evidence}
    supporting = [i for g in s.groups_for for i in g]
    prompt = load_prompt(PROMPT)
    text = prompt.render(claim_en=claim.claim_en, supporting_json=_items(supporting, by_id),
                         contradicting_json=_items(list(verdict.evidence_against_ids), by_id))
    try:
        review = await llm.generate(stage="score_upgrade", prompt=text, prompt_version=prompt.version,
                                    schema=ScoreUpgradeReview, timeout_s=timeout_s)
    except StageFailed as e:
        log_event(log, "score upgrade review failed", logging.WARNING, reason=str(e)[:300])
        return None
    kept = [i for i in review.kept_ids if i in supporting]
    if not review.accept or not kept:
        log_event(log, "score upgrade declined", claim_id=claim.claim_id, reason=review.reason_en[:300])
        return None
    # Re-score on what the Critic kept: still two independent groups and above the cutoff.
    upgraded = verdict.model_copy(update={
        "label": Label.TRUE, "evidence_for_ids": kept, "cited_ids": kept,
        "what_is_true_en": review.what_is_true_en or verdict.what_is_true_en,
        "reasoning_en": f"Evidence score upgrade: {review.reason_en}"})
    rescored = await source_policy.evidence_score(upgraded, evidence, claim_type=claim.claim_type,
                                                  claim_en=claim.claim_en, embed=embed)
    if rescored.p_true < rescored.cutoff or len(rescored.groups_for) < 2 or rescored.strong_against:
        return None
    upgraded = upgraded.model_copy(update={"confidence": min(99, round(100 * rescored.p_true))})
    policy = source_policy.check(upgraded, evidence)
    if not policy.passed:
        log_event(log, "score upgrade blocked by source policy", claim_id=claim.claim_id, reason=policy.reason)
        return None
    log_event(log, "score upgrade accepted", claim_id=claim.claim_id, p=round(rescored.p_true, 3), kept=kept)
    return upgraded, rescored
