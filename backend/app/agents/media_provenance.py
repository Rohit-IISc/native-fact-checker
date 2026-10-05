"""Media provenance agent (prompts/06_media_provenance_agent.md): earliest appearances of the image or
video keyframes via Cloud Vision web detection, with real publish dates read from the matching pages.
Skipped for text-only shares."""
from __future__ import annotations

import asyncio
import json

from app.agents.common import claim_ids, claims_json, finalize
from app.agents.tools import Tools
from app.intake import media as media_lane
from app.llm import LLM
from app.models import AgentFindings, CheckRequest, Extraction, FetchedPost
from app.prompts import load_prompt

PROMPT = "06_media_provenance_agent.md"
AGENT = "media_provenance"
MAX_VISION_CALLS = 5
MAX_DATED_PAGES = 6


def has_media(req: CheckRequest, fetched: FetchedPost | None) -> bool:
    return any(m.kind in ("image", "video") for m in req.media) or bool(fetched and fetched.image_uris)


async def _targets(req: CheckRequest, fetched: FetchedPost | None) -> list[tuple[str, str | None, bytes | None]]:
    """(label, uri, bytes) for each image and video keyframe, max 5."""
    out: list[tuple[str, str | None, bytes | None]] = []
    for i, m in enumerate(req.media):
        if m.kind == "image":
            out.append((f"image {i + 1}", m.uri, None))
        elif m.kind == "video":
            for j, frame in enumerate(await media_lane.keyframes(m.uri, 3, m.duration_s)):
                out.append((f"video keyframe {j + 1}", None, frame))
    for k, uri in enumerate(fetched.image_uris if fetched else []):
        out.append((f"link image {k + 1}", uri, None))
    return out[:MAX_VISION_CALLS]


async def run(llm: LLM, tools: Tools, extraction: Extraction, req: CheckRequest, fetched: FetchedPost | None,
              timeout_s: float) -> AgentFindings:
    targets = await _targets(req, fetched)
    detections = await asyncio.gather(*(tools.vision_web_detection(uri, content) for _, uri, content in targets))
    results = [{"media": label, **d} for (label, _, _), d in zip(targets, detections, strict=True)]
    pages = sorted({(p["url"], p["full_matches"]) for r in results for p in r.get("pages", [])},
                   key=lambda x: -x[1])
    dated = [u for u, _ in pages[:MAX_DATED_PAGES]]
    dates = dict(zip(dated, await asyncio.gather(*(tools.page_date(u) for u in dated)), strict=True))
    for r in results:
        for p in r.get("pages", []):
            p["published_at"] = dates.get(p["url"])
    urls = {p["url"] for r in results for p in r.get("pages", [])}
    signals = extraction.ai_generation_signals.model_dump() if extraction.ai_generation_signals else {}
    prompt = load_prompt(PROMPT)
    text = prompt.render(
        claims_json=claims_json(extraction, with_queries=False),
        extractor_ai_signals="extractor visual cues: " + json.dumps(signals, ensure_ascii=False),
        tool_results_json=json.dumps(results, ensure_ascii=False, indent=1),
    )
    findings = await llm.generate(stage=AGENT, prompt=text, prompt_version=prompt.version, schema=AgentFindings,
                                  timeout_s=timeout_s)
    return finalize(findings, AGENT, claim_ids(extraction), urls)
