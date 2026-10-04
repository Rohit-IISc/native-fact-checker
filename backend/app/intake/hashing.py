"""Tier 1 cache keys: sha256 of bytes, normalized text, normalized URL (pHash keys added with media)."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_FORWARD_MARKERS = re.compile(
    r"(forwarded( many times)?|फ़ॉरवर्ड किया गया|फॉरवर्ड किया गया|அனுப்பப்பட்டது|ಫಾರ್ವರ್ಡ್ ಮಾಡಲಾಗಿದೆ|diteruskan)",
    re.IGNORECASE,
)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'()]+", re.IGNORECASE)
_TRACKING_PARAMS = {
    "fbclid", "gclid", "igshid", "igsh", "si", "feature", "ref", "ref_src", "ref_url", "s", "t",
    "mibextid", "share_id", "utm_id",
}


def _is_emoji_or_symbol(ch: str) -> bool:
    cat = unicodedata.category(ch)
    # So: other symbols (emoji, dingbats); Sk: modifier symbols; Cf would remove ZWJ/ZWNJ which
    # Indic scripts need, so only drop variation selectors and the emoji ZWJ sequences' selectors.
    return cat == "So" or cat == "Sk" or ch in "️︎"


def normalize_text(text: str) -> str:
    """NFKC, lowercase, forward markers and emojis removed, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text)
    t = t.lower()
    t = _FORWARD_MARKERS.sub(" ", t)
    t = "".join(ch for ch in t if not _is_emoji_or_symbol(ch))
    return re.sub(r"\s+", " ", t).strip()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_key(text: str) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    return "text:" + sha256_hex(norm.encode("utf-8"))


def bytes_key(data: bytes) -> str:
    return "sha256:" + sha256_hex(data)


def normalize_url(url: str) -> str:
    """Lowercase scheme and host, drop fragment, default ports, tracking params; sort the query."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "m.youtube.com" or host == "mobile.twitter.com":
        host = host.split(".", 1)[1]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def url_key(url: str) -> str:
    return "url:" + sha256_hex(normalize_url(url).encode("utf-8"))


def extract_urls(text: str | None) -> list[str]:
    """WhatsApp often puts the link inside the text instead of the url field."""
    if not text:
        return []
    return [u.rstrip(".,;:!?)]}") for u in _URL_IN_TEXT.findall(text)]
