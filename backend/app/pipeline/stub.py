"""Day 1 stand-ins for the fan-out, panel and composer. Replaced stage by stage (Days 3 to 5).

A stub verdict is always NOT_ENOUGH_EVIDENCE: with no evidence the source policy would force
that label anyway, so the stub never shows an unsupported verdict.
"""
from __future__ import annotations

from app.models import AnswerText, Claim, JudgeVerdict, Label, band_for


def stub_judge(claim: Claim) -> JudgeVerdict:
    return JudgeVerdict(
        claim_id=claim.claim_id,
        label=Label.NOT_ENOUGH_EVIDENCE,
        confidence=0,
        what_is_true_en="We have not searched for evidence on this claim yet.",
        evidence_for_ids=[],
        evidence_against_ids=[],
        cited_ids=[],
        reasoning_en="Stub verdict: evidence search is not built yet.",
    )


_CONFIDENCE_PHRASE = {"HIGH": "We are very sure.", "MEDIUM": "We are fairly sure.", "LOW": "We are not sure."}


def stub_answer(claim: Claim, verdict: JudgeVerdict, language: str) -> AnswerText:
    band = band_for(verdict.confidence)
    claim_text = claim.claim_original if not language.startswith("en") else claim.claim_en
    headline = "Not confirmed yet: we could not check this claim"
    script = (
        f"The post claims: {claim.claim_en} "
        "We could not confirm this either way yet. "
        f"{verdict.what_is_true_en} "
        f"{_CONFIDENCE_PHRASE[band]} "
        "Please do not forward it until it is confirmed by a trusted source."
    )
    return AnswerText(
        language=language,
        headline=headline,
        summary="We could not confirm this claim either way. Please do not forward it until it is confirmed.",
        what_post_claims=claim_text,
        what_is_true=verdict.what_is_true_en,
        evidence_for=[],
        evidence_against=[],
        confidence_phrase=_CONFIDENCE_PHRASE[band],
        sources_spoken="",
        audio_script=script,
        card_lines=["Not confirmed", claim.claim_en[:80], "Do not forward until confirmed"],
    )


NON_CHECKABLE_MESSAGES = {
    "OPINION": "This post is an opinion. There is no fact to check.",
    "SATIRE": "This post is satire. It is not meant to be read as news.",
    "JOKE": "This post is a joke. There is no fact to check.",
    "GREETING": "This is a greeting message. There is nothing to fact-check.",
    "PROMOTION": "This post is an advertisement or promotion. There is no factual claim to check.",
    "DEVOTIONAL": "This is a devotional message. There is nothing to fact-check.",
    "PERSONAL_MESSAGE": "This is a personal message. There is nothing to fact-check.",
    "OTHER": "We did not find a factual claim to check in this post.",
}
