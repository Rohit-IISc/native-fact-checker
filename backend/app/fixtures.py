"""Recorded-style model outputs for LLM_MODE=fake (offline UI work) and tests. No paid calls."""
from __future__ import annotations

import json
import re

from app.models import Claim, ClaimType, Extraction, NonCheckableType, TimeSensitivity

_SCRIPTS = [
    (re.compile(r"[ऀ-ॿ]"), "hi-IN", "Deva"),
    (re.compile(r"[஀-௿]"), "ta-IN", "Taml"),
    (re.compile(r"[ಀ-೿]"), "kn-IN", "Knda"),
]
_GREETING = re.compile(r"good morning|suprabhat|सुप्रभात|शुभ प्रभात|காலை வணக்கம்|ಶುಭೋದಯ|selamat pagi", re.I)
_INDONESIAN = re.compile(r"\b(yang|dan|tidak|ini|itu|dengan|untuk|adalah)\b", re.I)


def user_content(prompt: str) -> str:
    # The shared rules mention the tag inline; the real block is the last one, on its own lines.
    blocks = re.findall(r"^<user_content>\n(.*?)\n</user_content>$", prompt, re.S | re.M)
    return blocks[-1].strip() if blocks else ""


def detect_language(text: str) -> tuple[str, str]:
    for rx, lang, script in _SCRIPTS:
        if rx.search(text):
            return lang, script
    if len(_INDONESIAN.findall(text)) >= 2:
        return "id-ID", "Latn"
    return "en-IN", "Latn"


def fake_extraction(prompt: str) -> Extraction:
    text = user_content(prompt)
    lang, script = detect_language(text)
    if not text or _GREETING.search(text):
        return Extraction(
            content_language=lang, content_script=script,
            summary_en="A greeting message." if text else "Empty share.",
            checkable=False, non_checkable_type=NonCheckableType.GREETING,
        )
    sentence = re.split(r"(?<=[.!?।])\s+", text)[0][:300]
    return Extraction(
        content_language=lang,
        content_script=script,
        summary_en=f"A forwarded message making a claim ({lang}).",
        checkable=True,
        claims=[Claim(
            claim_id="c1",
            claim_original=sentence,
            claim_en=sentence if lang.startswith("en") else f"[fake translation] {sentence}",
            claim_type=ClaimType.OTHER,
            time_sensitivity=TimeSensitivity.EVERGREEN,
            search_queries_original=[sentence[:60]],
            search_queries_en=[sentence[:60]],
        )],
    )


def _claim_ids(prompt: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'"claim_id": "([^"]+)"', prompt)))


def fake_judge(prompt: str) -> dict:
    """No evidence offline, so the honest verdict is NOT_ENOUGH_EVIDENCE."""
    return {"verdicts": [{
        "claim_id": cid, "label": "NOT_ENOUGH_EVIDENCE", "confidence": 20,
        "what_is_true_en": "No credible source confirms or denies this claim.",
        "evidence_for_ids": [], "evidence_against_ids": [], "cited_ids": [],
        "reasoning_en": "Offline mode: no evidence was gathered.",
    } for cid in _claim_ids(prompt)]}


def fake_critic(prompt: str) -> dict:
    ids = list(dict.fromkeys(re.findall(r'"claim_id": "([^"]+)"', prompt.split("Judge's verdicts:")[-1])))
    return {"reviews": [{"claim_id": cid, "decision": "AGREE", "proposed_label": "NOT_ENOUGH_EVIDENCE",
                         "proposed_confidence": 20, "objections_en": []} for cid in ids]}


def fake_composer(prompt: str) -> dict:
    from app.models import Claim, ClaimType, JudgeVerdict, Label, TimeSensitivity
    from app.pipeline.stub import stub_answer

    lang = (re.search(r"\(([a-z]{2,3}-[A-Za-z]{2,4}|[a-z]{2,3}), script", prompt) or [None, "en"])[1]
    lang = "en" if lang.startswith("en") else lang
    data = json.loads(prompt.split("Verdict data:", 1)[1].split("Return JSON", 1)[0])
    claim = Claim(claim_id="c1", claim_original=data["claim_original"], claim_en=data["claim_en"],
                  claim_type=ClaimType.OTHER, time_sensitivity=TimeSensitivity.EVERGREEN)
    v = JudgeVerdict(claim_id="c1", label=Label(data["label"]), confidence=data["confidence"],
                     what_is_true_en=data["what_is_true_en"], evidence_for_ids=[], evidence_against_ids=[],
                     cited_ids=[], reasoning_en="")
    return stub_answer(claim, v, lang).model_dump()


def demo_fixtures() -> dict:
    """Offline outputs for every stage (LLM_MODE=fake). Agents find nothing, so verdicts are NEE."""
    return {
        "extractor": fake_extraction,
        "web_search": {"text": "Offline mode: no search was run.", "sources": [], "queries": 0},
        "factcheck_sites": {"agent": "factcheck_sites", "evidence": [], "notes_en": "offline"},
        "source_credibility": {"agent": "source_credibility", "evidence": [], "source_assessment": {
            "origin_type": "UNKNOWN", "note_en": "Offline mode: origin not assessed."}},
        "media_provenance": {"agent": "media_provenance", "evidence": [], "notes_en": "offline"},
        "judge": fake_judge,
        "critic": fake_critic,
        "composer": fake_composer,
    }
