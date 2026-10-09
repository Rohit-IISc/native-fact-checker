"""Fact-check sites agent (prompts/04_factcheck_agent.md): Fact Check Tools API, then Flash classifies."""
from __future__ import annotations

import asyncio
import json
import re

from app.agents.common import claim_ids, claims_json, finalize
from app.agents.tools import Tools
from app.llm import LLM
from app.models import AgentFindings, Extraction
from app.prompts import load_prompt

PROMPT = "04_factcheck_agent.md"
AGENT = "factcheck_sites"
MAX_REVIEWS = 15


_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _variants(queries: list[str]) -> list[str]:
    """The first two queries, each also without years: the API matches keywords literally, and a
    recycled hoax fact-checked in 2023 does not mention "2026"."""
    out = []
    for q in queries[:2]:
        out.append(q)
        stripped = " ".join(_YEAR.sub(" ", q).split())
        if stripped and stripped != q:
            out.append(stripped)
    return out


def search_plan(extraction: Extraction) -> list[tuple[str, str]]:
    """(query, languageCode) pairs: original language, English, and Hindi for other Indian languages."""
    lang = extraction.content_language.split("-")[0].lower()
    plan: list[tuple[str, str]] = []
    for c in extraction.claims:
        plan += [(q, lang) for q in _variants(c.search_queries_original or [c.claim_original[:150]])]
        plan += [(q, "en") for q in _variants(c.search_queries_en or [c.claim_en[:150]])]
        if lang in ("ta", "kn", "te", "ml", "mr", "bn", "gu", "pa", "or"):
            # Many Indian fact checks are published in Hindi or English first.
            plan.append((c.claim_en[:150], "hi"))
        # The same claim in the other Indian demo languages: the API matches words, so a Tamil fact check
        # is only found with Tamil words (eval recall at 5 for kn->hi and ta->kn was 0-5%, Oct 9).
        plan += [(r.query, r.language) for r in c.search_queries_regional if r.language != lang and r.query.strip()]
        # No language filter: a fact check published in another language (a Tamil check of a claim that
        # reached us in Kannada) is invisible to the filtered searches above (eval recall at 5, Oct 9).
        plan += [(q, "") for q in (c.search_queries_en or [c.claim_en[:150]])[:1]]
        plan += [(q, "") for q in (c.search_queries_original or [c.claim_original[:150]])[:1]]
    # Text printed on the photo or video ("DELHI संकट मे"): earlier fact checks of the same media were written
    # about the story it was first shared with, not the new caption (case 01, Oct 9). Prompts alone did not
    # always put it in the queries, so code does.
    if extraction.ocr_text and extraction.claims:
        printed = " ".join(extraction.ocr_text.split())[:80]
        if len(printed) >= 6:
            plan += [(printed, ""), (f"{printed} fact check", "en")]
    seen: set[tuple[str, str]] = set()
    return [p for p in plan if not (p in seen or seen.add(p))]


async def run(llm: LLM, tools: Tools, extraction: Extraction, timeout_s: float) -> AgentFindings:
    results = await asyncio.gather(*(tools.factcheck_search(q, lang) for q, lang in search_plan(extraction)))
    reviews, urls = [], set()
    for batch in results:
        for r in batch:
            if r.get("url") and r["url"] not in urls:
                urls.add(r["url"])
                reviews.append(r)
    if not reviews:
        return AgentFindings(agent=AGENT, notes_en="No published fact checks matched the claims.")
    prompt = load_prompt(PROMPT)
    text = prompt.render(claims_json=claims_json(extraction, with_queries=False),
                         tool_results_json=json.dumps(reviews[:MAX_REVIEWS], ensure_ascii=False, indent=1))
    findings = await llm.generate(stage=AGENT, prompt=text, prompt_version=prompt.version, schema=AgentFindings,
                                  timeout_s=timeout_s)
    return finalize(findings, AGENT, claim_ids(extraction), urls)
