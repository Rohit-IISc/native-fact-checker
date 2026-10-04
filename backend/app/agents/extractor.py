"""Information extractor (Gemini Flash, prompts/01_extractor.md)."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from app.intake.links import platform_of
from app.llm import LLM, MediaPart
from app.models import CheckRequest, Extraction, FetchedPost
from app.prompts import load_prompt
from app.settings import get_config

PROMPT = "01_extractor.md"


def media_seconds(req: CheckRequest) -> float:
    """Seconds of audio/video Gemini will watch; sets the extraction timeout and the check budget.

    A YouTube link has no known duration here, so it counts as the full max_media_seconds clip.
    """
    seconds = sum(m.duration_s or 0 for m in req.media if m.kind in ("video", "audio"))
    if req.url and platform_of(req.url) == "youtube":
        seconds += float(get_config().limits["input"]["max_media_seconds"])
    return seconds


def build_prompt(req: CheckRequest, fetched: FetchedPost | None) -> tuple[str, str]:
    prompt = load_prompt(PROMPT)
    link_meta = {}
    if fetched:
        link_meta = {
            "source_url": fetched.source_url, "title": fetched.title,
            "author_handle": fetched.author_handle,
            "published_at": fetched.published_at.isoformat() if fetched.published_at else None,
            "media_missing": fetched.media_missing,
        }
    text = prompt.render(
        share_date=req.share_date.isoformat(),
        platform=fetched.platform if fetched else "none",
        link_metadata=json.dumps(link_meta, ensure_ascii=False) if link_meta else "none",
        shared_text=req.text or "",
        fetched_text=(fetched.text or "") if fetched else "",
    )
    return text, prompt.version


def media_parts(req: CheckRequest, fetched: FetchedPost | None) -> list[MediaPart]:
    limits = get_config().limits["input"]
    low_res = media_seconds(req) > limits["low_media_resolution_over_seconds"]
    parts = [
        MediaPart(mime_type=m.mime_type, low_resolution=low_res and m.kind == "video",
                  end_offset_s=limits["max_media_seconds"] if m.kind in ("video", "audio") else None,
                  **_media_source(m.uri))
        for m in req.media
    ]
    if fetched:
        parts += [MediaPart(mime_type=mimetypes.guess_type(u)[0] or "image/jpeg", **_media_source(u))
                  for u in fetched.image_uris]
        if fetched.youtube_url:
            parts.append(MediaPart(mime_type="video/mp4", uri=fetched.youtube_url,
                                   end_offset_s=limits["max_media_seconds"], low_resolution=True))
    return parts


def _media_source(uri: str) -> dict:
    """gs:// and https:// go by reference; a local path (make try FILE=..., dev only) goes inline."""
    if uri.startswith(("gs://", "http://", "https://")):
        return {"uri": uri}
    return {"data": Path(uri).read_bytes()}


def finalize(extraction: Extraction) -> Extraction:
    """Assign stable claim ids, enforce the claim cap, keep NOT_CHECKABLE consistent."""
    max_claims = int(get_config().limits["input"]["max_claims_per_check"])
    claims = extraction.claims[:max_claims]
    extra = list(extraction.extra_claims_not_checked) + [c.claim_en for c in extraction.claims[max_claims:]]
    claims = [c.model_copy(update={"claim_id": f"c{i + 1}"}) for i, c in enumerate(claims)]
    checkable = extraction.checkable and bool(claims)
    update = {"claims": claims if checkable else [], "extra_claims_not_checked": extra, "checkable": checkable}
    if not checkable and extraction.non_checkable_type is None:
        update["non_checkable_type"] = "OTHER"
    return extraction.model_copy(update=update)


def has_content(req: CheckRequest, fetched: FetchedPost | None) -> bool:
    """Anything for the model to read. With nothing, Gemini has been seen inventing a claim."""
    fetched_any = bool(fetched and (fetched.text or fetched.title or fetched.image_uris or fetched.youtube_url))
    return bool((req.text or "").strip() or req.media or fetched_any)


async def extract(llm: LLM, req: CheckRequest, fetched: FetchedPost | None = None) -> Extraction:
    if not has_content(req, fetched):
        return Extraction(content_language="en-IN", content_script="Latn", summary_en="Nothing readable was shared.",
                          checkable=False, non_checkable_type="OTHER")
    text, version = build_prompt(req, fetched)
    timeout = get_config().extraction_timeout(media_seconds(req))
    result = await llm.generate(
        stage="extractor", prompt=text, prompt_version=version, schema=Extraction,
        media=media_parts(req, fetched), timeout_s=timeout,
    )
    return finalize(result)
