"""Recorded-style model outputs for LLM_MODE=fake (offline UI work) and tests. No paid calls."""
from __future__ import annotations

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


def demo_fixtures() -> dict:
    return {"extractor": fake_extraction}
