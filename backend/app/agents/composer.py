"""Answer composer (prompts/10_composer.md): the answer in the content language and in English."""
from __future__ import annotations

import asyncio
import json

from app.llm import LLM, StageFailed
from app.models import AnswerText, Claim, ComposerOutput, Evidence, JudgeVerdict, PanelOutcome, band_for
from app.prompts import load_prompt
from app.settings import get_config

PROMPT = "10_composer.md"
LANGUAGE_NAMES = {"hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "id": "Indonesian", "en": "English",
                  "te": "Telugu", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
                  "pa": "Punjabi", "ur": "Urdu", "or": "Odia"}


def _ev(e: Evidence) -> dict:
    return {"publisher": e.publisher or e.domain, "title": e.title, "says": e.snippet_en, "tier": e.tier.value,
            "date": e.published_at.isoformat() if e.published_at else None, "rating": e.rating_text}


def claim_result_json(claim: Claim, verdict: JudgeVerdict, outcome: PanelOutcome, evidence: list[Evidence],
                      split_readings: list[str] | None) -> str:
    by_id = {e.evidence_id: e for e in evidence}
    return json.dumps({
        "claim_original": claim.claim_original, "claim_en": claim.claim_en,
        "label": verdict.label.value, "confidence": verdict.confidence, "band": band_for(verdict.confidence),
        "what_is_true_en": verdict.what_is_true_en,
        "event_date": verdict.event_date.isoformat() if verdict.event_date else None,
        "evidence_for": [_ev(by_id[i]) for i in verdict.evidence_for_ids if i in by_id],
        "evidence_against": [_ev(by_id[i]) for i in verdict.evidence_against_ids if i in by_id],
        "ai_generation": verdict.ai_generation.model_dump() if verdict.ai_generation else None,
        "panel_outcome": outcome.value,
        "panel_disagreement": split_readings or None,
    }, ensure_ascii=False, indent=1)


# Unicode ranges of the scripts we answer in; Latin is checked as "no Indic letters".
_SCRIPT_RANGES = {"Deva": ("\u0900", "\u097f"), "Taml": ("\u0b80", "\u0bff"), "Knda": ("\u0c80", "\u0cff"),
                  "Telu": ("\u0c00", "\u0c7f"), "Mlym": ("\u0d00", "\u0d7f"), "Beng": ("\u0980", "\u09ff"),
                  "Gujr": ("\u0a80", "\u0aff"), "Guru": ("\u0a00", "\u0a7f")}


def script_matches(answer: AnswerText, script: str) -> bool:
    """True if the answer is written in `script`. Seen in testing: an en-IN answer written in Hindi."""
    text = f"{answer.headline} {answer.summary} {answer.what_is_true}"
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return True
    indic = sum(1 for ch in letters if "\u0900" <= ch <= "\u0dff")
    if script == "Latn":
        return indic / len(letters) < 0.2
    lo, hi = _SCRIPT_RANGES.get(script, ("\u0000", "\uffff"))
    return sum(1 for ch in letters if lo <= ch <= hi) / len(letters) >= 0.5


def verdict_word(label: str, language: str) -> str:
    """The verdict in the answer language, the same word the card and the app show (config/languages.yaml)."""
    langs = get_config().languages.get("demo_languages") or {}
    words = ((langs.get(language) or langs.get("en") or {}).get("card") or {}).get("labels") or {}
    return words.get(label) or label.replace("_", " ").lower()


async def _write(llm: LLM, data: str, language: str, script: str) -> AnswerText:
    prompt = load_prompt(PROMPT)
    base = language.split("-")[0].lower()
    name = LANGUAGE_NAMES.get(base, language)
    # "en-IN" invited Hindi answers ("IN" -> India); English is just English.
    shown = "en" if base == "en" else language
    label = json.loads(data).get("label") or ""
    text = prompt.render(answer_language_name=name, answer_language=shown, answer_script=script,
                         claim_result_json=data, label=label, verdict_word=verdict_word(label, base))
    timeout = get_config().timeout("composer")
    out = await llm.generate(stage="composer", prompt=text, prompt_version=prompt.version, schema=AnswerText,
                             timeout_s=timeout)
    if not script_matches(out, script):
        out = await llm.generate(
            stage="composer", prompt_version=prompt.version, schema=AnswerText, timeout_s=timeout,
            prompt=f"{text}\n\nYour previous answer was not written in {name}. Write every field in {name} "
                   f"({script} script) only.")
        if not script_matches(out, script):
            raise StageFailed("composer", f"answer not in {name} after retry")
    # The model sometimes echoes a short code; keep the exact language for routing and TTS.
    return out.model_copy(update={"language": language})


async def compose(llm: LLM, claim: Claim, verdict: JudgeVerdict, outcome: PanelOutcome, evidence: list[Evidence],
                  split_readings: list[str] | None, language: str, script: str) -> ComposerOutput:
    """Native and English answers as two parallel calls (half the output each, so about half the
    latency of one call writing both). An English post needs only one."""
    data = claim_result_json(claim, verdict, outcome, evidence, split_readings)
    if language.split("-")[0].lower() == "en":
        native = await _write(llm, data, language, script)
        return ComposerOutput(native=native, english=native.model_copy(update={"language": "en"}))
    native, english = await asyncio.gather(_write(llm, data, language, script), _write(llm, data, "en", "Latn"))
    return ComposerOutput(native=native, english=english)


async def translate(llm: LLM, answer_en: AnswerText, language: str, script: str) -> AnswerText:
    """Composer TRANSLATE MODE: a cached verdict's English answer, written in a new content language."""
    prompt = load_prompt(PROMPT, section="translate")
    name = LANGUAGE_NAMES.get(language.split("-")[0].lower(), language)
    text = (prompt.render(answer_language_name=name)
            + f"\n\nEnglish AnswerText:\n<user_content>\n{answer_en.model_dump_json(indent=1)}\n</user_content>")
    timeout = get_config().timeout("composer")
    out = await llm.generate(stage="composer", prompt=text, prompt_version=prompt.version, schema=AnswerText,
                             timeout_s=timeout)
    if not script_matches(out, script):
        raise StageFailed("composer", f"translation not in {name}")
    return out.model_copy(update={"language": language})


_HEADLINE = {"TRUE": "True", "FALSE": "False", "MISLEADING": "Misleading", "SCAM": "Scam",
             "NOT_ENOUGH_EVIDENCE": "Not confirmed"}


def fallback_answer(claim: Claim, verdict: JudgeVerdict, evidence: list[Evidence],
                    split_readings: list[str] | None = None) -> AnswerText:
    """English answer from the verdict itself, used only if the composer fails."""
    by_id = {e.evidence_id: e for e in evidence}
    name = lambda i: by_id[i].publisher or by_id[i].domain or "a source"  # noqa: E731
    sources = list(dict.fromkeys(name(i) for i in verdict.cited_ids if i in by_id))[:3]
    phrase = {"HIGH": "We are very sure.", "MEDIUM": "We are fairly sure.", "LOW": "We are not sure."}[
        band_for(verdict.confidence)]
    head = _HEADLINE[verdict.label.value]
    spoken = f"according to {' and '.join(sources)}" if sources else ""
    return AnswerText(
        language="en", headline=f"{head}: {claim.claim_en}"[:90], summary=verdict.what_is_true_en,
        what_post_claims=claim.claim_en, what_is_true=verdict.what_is_true_en,
        evidence_for=[f"{name(i)}: {by_id[i].snippet_en}" for i in verdict.evidence_for_ids if i in by_id][:3],
        evidence_against=[f"{name(i)}: {by_id[i].snippet_en}" for i in verdict.evidence_against_ids if i in by_id][:3],
        confidence_phrase=phrase, sources_spoken=spoken,
        audio_script=f"The post claims: {claim.claim_en}. Our verdict: {head}. {verdict.what_is_true_en} "
                     f"{phrase} {spoken}".strip(),
        card_lines=[head, claim.claim_en[:80], verdict.what_is_true_en[:80]],
        panel_readings=list(split_readings or []),
        ai_signals_ai=list(verdict.ai_generation.signals_ai) if verdict.ai_generation else [],
        ai_signals_real=list(verdict.ai_generation.signals_real) if verdict.ai_generation else [],
    )
