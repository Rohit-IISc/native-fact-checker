"""Source credibility agent (prompts/05_source_credibility_agent.md): where did the post come from.

Code gathers the signals (offender record, domain age, lookalike domains); Flash writes the
SourceAssessment. Skipped when there is no origin information at all.
"""
from __future__ import annotations

import asyncio
import json
import re

from app.agents.tools import Tools, source_key
from app.llm import LLM
from app.models import AgentFindings, Extraction, FetchedPost, SourceTier
from app.prompts import load_prompt
from app.settings import get_config
from app.verify.source_tiers import host_of, tier_for_url

PROMPT = "05_source_credibility_agent.md"
AGENT = "source_credibility"
_HANDLE = re.compile(r"^@?[A-Za-z0-9_.]{2,30}$")
_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.I)


def origins(extraction: Extraction, fetched: FetchedPost | None) -> tuple[list[str], list[str]]:
    """(domains, handles) worth looking up."""
    domains, handles = [], []
    if fetched and fetched.source_url:
        domains.append(host_of(fetched.source_url))
    if fetched and fetched.author_handle:
        handles.append("@" + fetched.author_handle.lstrip("@"))
    for hint in extraction.origin_hints:
        h = hint.strip()
        if h.startswith("@") and _HANDLE.match(h):
            handles.append(h)
        elif _DOMAIN.match(h.removeprefix("www.")):
            domains.append(host_of(h))
    dedupe = lambda xs: list(dict.fromkeys(x.lower() for x in xs if x))  # noqa: E731
    return dedupe(domains)[:3], dedupe(handles)[:3]


def has_origin(extraction: Extraction, fetched: FetchedPost | None) -> bool:
    d, h = origins(extraction, fetched)
    return bool(d or h or extraction.origin_hints)


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lookalikes(domain: str) -> list[str]:
    """Known tier 1/2 outlets this domain imitates (ndtv-news.co -> ndtv.com)."""
    if tier_for_url(domain) in (SourceTier.TIER_1, SourceTier.TIER_2, SourceTier.NOT_A_SOURCE):
        return []
    label = domain.split(".")[0]
    cfg = get_config().source_tiers
    known = [d.split("/")[0] for k in ("tier_1", "tier_2") for d in (cfg.get(k) or {}).get("domains") or []]
    hits = []
    for k in dict.fromkeys(known):
        name = k.split(".")[0]
        if len(name) < 4:
            continue
        if (name in label and label != name) or 0 < _distance(label, name) <= 2:
            hits.append(k)
    return hits[:3]


async def run(llm: LLM, tools: Tools, extraction: Extraction, fetched: FetchedPost | None,
              timeout_s: float) -> AgentFindings:
    domains, handles = origins(extraction, fetched)
    lookups = await asyncio.gather(*(tools.lookup_source(k) for k in domains + handles))
    results: dict[str, dict] = {}
    for key, rec in zip(domains + handles, lookups, strict=True):
        results[source_key(key)] = {"offender_record": rec or None, "tier": tier_for_url(key).value
                                    if not key.startswith("@") else None}
    unknown_sites = [d for d in domains if tier_for_url(d) == SourceTier.TIER_3]
    ages = await asyncio.gather(*(tools.domain_info(d) for d in unknown_sites))
    for d, age in zip(unknown_sites, ages, strict=True):
        results[source_key(d)] |= {"domain_info": age or None, "lookalike_of": lookalikes(d)}
    prompt = load_prompt(PROMPT)
    text = prompt.render(
        source_url=fetched.source_url if fetched else "none",
        author_handle=(fetched.author_handle if fetched else None) or "none",
        origin_hints=", ".join(extraction.origin_hints) or "none",
        tool_results_json=json.dumps(results, ensure_ascii=False, indent=1, default=str),
    )
    findings = await llm.generate(stage=AGENT, prompt=text, prompt_version=prompt.version, schema=AgentFindings,
                                  timeout_s=timeout_s)
    # This agent rates the origin; it does not contribute evidence items.
    return findings.model_copy(update={"agent": AGENT, "evidence": []})
