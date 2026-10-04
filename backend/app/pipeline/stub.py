"""Day 1 stand-ins for the fan-out, panel and composer. Replaced stage by stage (Days 3 to 5).

A stub verdict is always NOT_ENOUGH_EVIDENCE: with no evidence the source policy would force
that label anyway, so the stub never shows an unsupported verdict.
"""
from __future__ import annotations

from app.models import AnswerText, Claim, JudgeVerdict, Label, band_for
from app.settings import get_config


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


def messages(language: str | None) -> dict:
    """Fixed answer text in `language` (BCP-47) from config/messages.yaml, English if not listed."""
    all_msgs = get_config().messages
    base = (language or "en").split("-")[0].lower()
    return all_msgs.get(base) or all_msgs["en"]


def non_checkable_message(non_checkable_type: str, language: str | None) -> str:
    texts = messages(language)["non_checkable"]
    return texts.get(non_checkable_type) or texts["OTHER"]


def stub_answer(claim: Claim, verdict: JudgeVerdict, language: str) -> AnswerText:
    """The whole answer is in `language` (decision 15); only the English variant quotes claim_en."""
    m = messages(language)["stub"]
    band = band_for(verdict.confidence)
    claim_text = claim.claim_en if language.startswith("en") else claim.claim_original
    script = (
        f"{m['post_claims']} {claim_text} {m['could_not_confirm']} {m['what_is_true']} "
        f"{m['confidence'][band]} {m['do_not_forward']}"
    )
    return AnswerText(
        language=language,
        headline=m["headline"],
        summary=m["summary"],
        what_post_claims=claim_text,
        what_is_true=m["what_is_true"],
        evidence_for=[],
        evidence_against=[],
        confidence_phrase=m["confidence"][band],
        sources_spoken="",
        audio_script=script,
        card_lines=[m["card_title"], claim_text[:80], m["card_footer"]],
    )
