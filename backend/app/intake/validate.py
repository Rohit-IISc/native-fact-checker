"""Input validation against config/limits.yaml. File types are checked by magic bytes, not extension."""
from __future__ import annotations

from dataclasses import dataclass

from app.settings import get_config


class InvalidInput(Exception):
    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code


@dataclass
class UploadedFile:
    filename: str
    data: bytes
    declared_type: str | None = None


def sniff(data: bytes) -> tuple[str, str] | None:
    """Return (kind, mime) from magic bytes, or None if unsupported."""
    head = data[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "audio/wav"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return "image", "image/heic"
        if brand in (b"M4A ", b"M4B "):
            return "audio", "audio/mp4"
        if brand.startswith(b"3g"):
            return "video", "video/3gpp"
        if brand == b"qt  ":
            return "video", "video/quicktime"
        return "video", "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", "video/webm"
    if head.startswith(b"OggS"):
        return "audio", "audio/ogg"     # WhatsApp voice notes (Opus in Ogg)
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio", "audio/mpeg"
    return None


def validate(text: str | None, url: str | None, files: list[UploadedFile]) -> list[tuple[UploadedFile, str, str]]:
    """Validate a share. Returns [(file, kind, mime)]. Raises InvalidInput with the API error_code."""
    lim = get_config().limits["input"]
    if not (text and text.strip()) and not (url and url.strip()) and not files:
        raise InvalidInput("EMPTY", "Nothing to check")
    if text and len(text) > int(lim["max_text_chars"]):
        raise InvalidInput("TOO_LARGE", f"Text over {lim['max_text_chars']} characters")
    total = sum(len(f.data) for f in files) + len((text or "").encode())
    if total > int(lim["max_share_bytes"]):
        raise InvalidInput("TOO_LARGE", "Share is over 50 MB")
    typed = []
    for f in files:
        sniffed = sniff(f.data)
        if sniffed is None:
            raise InvalidInput("UNSUPPORTED_TYPE", f"Unsupported file: {f.filename}")
        typed.append((f, *sniffed))
    images = [t for t in typed if t[1] == "image"]
    av = [t for t in typed if t[1] in ("video", "audio")]
    if len(images) > int(lim["max_images"]) or len(av) > 1 or (av and images):
        raise InvalidInput("TOO_MANY_FILES", "Up to 10 images, or one video or audio clip")
    return typed
