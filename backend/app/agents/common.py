"""Helpers shared by the fan-out agents: claim serialisation and code-assigned evidence fields.

The model never sets an evidence id, a tier or a domain, and an evidence URL survives only if a tool
(search, fact-check API, Vision) actually returned it. That is the anti-hallucination floor under
the source policy.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from app.models import AgentFindings, Claim, Evidence, Extraction
from app.verify.source_tiers import host_of, tier_for_url

PREFIX = {"web_search": "ws", "factcheck_sites": "fc", "source_credibility": "sc", "media_provenance": "mp"}


def claims_json(extraction: Extraction, *, with_queries: bool = True) -> str:
    def one(c: Claim) -> dict:
        d = {"claim_id": c.claim_id, "claim_original": c.claim_original, "claim_en": c.claim_en,
             "claim_type": c.claim_type.value, "place": c.place,
             "claimed_date": c.claimed_date.isoformat() if c.claimed_date else None, "entities": c.entities}
        if with_queries:
            d |= {"search_queries_original": c.search_queries_original, "search_queries_en": c.search_queries_en}
        return d

    return json.dumps([one(c) for c in extraction.claims], ensure_ascii=False, indent=1)


def _norm(url: str) -> str:
    p = urlsplit(url.strip())
    return f"{(p.hostname or '').removeprefix('www.')}{p.path.rstrip('/')}".lower()


def finalize(findings: AgentFindings, agent: str, claim_ids: set[str], allowed_urls: set[str] | None
             ) -> AgentFindings:
    """Assign ids, domains and tiers; drop evidence for unknown claims, UNRELATED items, and URLs no tool
    returned (allowed_urls=None means the agent has no URL source, so items need no URL)."""
    allowed = {_norm(u) for u in allowed_urls or set()}
    by_host: dict[str, list[str]] = {}
    for u in allowed_urls or set():
        by_host.setdefault(host_of(u), []).append(u)
    kept: list[Evidence] = []
    for e in findings.evidence:
        if e.claim_id not in claim_ids or e.stance.value == "UNRELATED":
            continue
        if allowed_urls is not None:
            if not e.url:
                continue
            if _norm(e.url) not in allowed:
                # The model sometimes trims or rewrites a URL. Substitute the real one only when the
                # host returned exactly one page; otherwise the URL may be invented: drop it.
                same_host = by_host.get(host_of(e.url), [])
                if len(same_host) != 1:
                    continue
                e = e.model_copy(update={"url": same_host[0]})
        kept.append(e)
    prefix = PREFIX.get(agent, agent[:2])
    out = [e.model_copy(update={
        "evidence_id": f"{prefix}-{i + 1}", "agent": agent,
        "domain": host_of(e.url) if e.url else e.domain,
        "tier": tier_for_url(e.url, e.domain),
    }) for i, e in enumerate(kept)]
    return findings.model_copy(update={"evidence": out, "agent": agent})


def claim_ids(extraction: Extraction) -> set[str]:
    return {c.claim_id for c in extraction.claims}
