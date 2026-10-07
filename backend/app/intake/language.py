"""Language of the user's own caption, without a model call.

Rule (Rohit, 2026-10-07): the caption the user shares decides the answer language, even when text
printed inside the media is in another language. The extractor applies it on a full check; this module
applies it on an instant tier 1 cache hit, where no model reads the share.
"""
from __future__ import annotations

import re

# Script -> (BCP-47, ISO 15924). Order matters only for mixed text: the script with most letters wins.
_SCRIPTS = {
    "Deva": ("hi-IN", "ऀ", "ॿ"),
    "Beng": ("bn-IN", "ঀ", "৿"),
    "Guru": ("pa-IN", "਀", "੿"),
    "Gujr": ("gu-IN", "઀", "૿"),
    "Orya": ("or-IN", "଀", "୿"),
    "Taml": ("ta-IN", "஀", "௿"),
    "Telu": ("te-IN", "ఀ", "౿"),
    "Knda": ("kn-IN", "ಀ", "೿"),
    "Mlym": ("ml-IN", "ഀ", "ൿ"),
}
_URL = re.compile(r"https?://\S+")
_INDONESIAN = re.compile(r"\b(yang|dan|tidak|ini|itu|dengan|untuk|adalah|di|ke|dari|sudah|akan|banjir|hari)\b",
                         re.I)


def caption_language(text: str | None) -> tuple[str, str] | None:
    """(language, script) of a caption, or None when it has no words to go by (empty, a bare link, emojis).

    Latin-script captions are English unless they read as Indonesian; romanised Hindi ("Hinglish") is
    reported as English, which the full pipeline's extractor would refine.
    """
    words = _URL.sub(" ", text or "")
    letters = [ch for ch in words if ch.isalpha()]
    if len(letters) < 3:
        return None
    counts = {code: sum(1 for ch in letters if lo <= ch <= hi) for code, (_, lo, hi) in _SCRIPTS.items()}
    best = max(counts, key=lambda k: counts[k])
    if counts[best] / len(letters) >= 0.3:
        return _SCRIPTS[best][0], best
    if len(_INDONESIAN.findall(words)) >= 2:
        return "id-ID", "Latn"
    return "en-IN", "Latn"


def same_language(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.split("-")[0].lower() == b.split("-")[0].lower()  # type: ignore[union-attr]
