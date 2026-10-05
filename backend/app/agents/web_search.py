"""Web search agent (prompts/03 and 03b): Gemini Flash with Grounding with Google Search, then a second
Flash call that turns the cited findings into evidence. Sources are referenced by number, so every
evidence URL is a page Google Search actually returned; the model never types a URL."""
from __future__ import annotations

import json
import time

from app.agents.common import claim_ids, claims_json, finalize
from app.llm import LLM
from app.models import AgentFindings, Evidence, Extraction, WebSearchOutput
from app.prompts import load_prompt
from app.settings import get_config

PROMPT = "03_web_search_agent.md"
CLASSIFY_PROMPT = "03b_web_search_classify.md"
AGENT = "web_search"


CLASSIFY_RESERVE_S = 6.0


async def run(llm: LLM, extraction: Extraction, timeout_s: float) -> AgentFindings:
    """timeout_s covers both calls: the search gets all but CLASSIFY_RESERVE_S, classify the rest."""
    deadline = time.monotonic() + timeout_s
    prompt = load_prompt(PROMPT)
    found = await llm.search(stage=AGENT, prompt_version=prompt.version,
                             timeout_s=max(5.0, timeout_s - CLASSIFY_RESERVE_S), prompt=prompt.render(
        max_queries=get_config().limits["web_search"]["max_grounded_queries"],
        content_language=extraction.content_language, claims_json=claims_json(extraction)))
    if not found.sources:
        return AgentFindings(agent=AGENT, notes_en="Web search returned no citable sources.")
    by_n = {s.n: s for s in found.sources}
    classify = load_prompt(CLASSIFY_PROMPT)
    out = await llm.generate(
        stage="web_search_classify", prompt_version=classify.version, schema=WebSearchOutput,
        timeout_s=max(3.0, deadline - time.monotonic()),
        prompt=classify.render(
            claims_json=claims_json(extraction, with_queries=False),
            sources_json=json.dumps([s.model_dump() for s in found.sources], ensure_ascii=False, indent=1),
            findings_text=found.text))
    evidence = [Evidence(evidence_id="", agent=AGENT, claim_id=i.claim_id, url=by_n[i.source_n].url,
                         publisher=i.publisher, title=i.title, published_at=i.published_at, language=i.language,
                         snippet_en=i.snippet_en, stance=i.stance)
                for i in out.items if i.source_n in by_n]
    findings = AgentFindings(agent=AGENT, evidence=evidence, notes_en=out.notes_en)
    return finalize(findings, AGENT, claim_ids(extraction), {s.url for s in found.sources})
