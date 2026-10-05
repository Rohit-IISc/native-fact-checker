"""Tier 2 cache: semantic claim match after extraction (docs/04).

Embed claim_en, find the nearest ACTIVE claims (Firestore vector search, cosine), and ask Flash
(prompts/02_near_match.md) whether each candidate is the same claim:
  SAME                      -> reuse the cached verdict for this claim
  SAME_CLAIM_DIFFERENT_DATE -> run the full pipeline with the cached verdict as context evidence
  DIFFERENT                 -> full pipeline
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.cache.tier1 import _usable
from app.llm import LLM, StageFailed
from app.models import AgentFindings, Claim, Evidence, Extraction, NearMatchResult, Stance
from app.observability.logging import log_event
from app.pipeline.results import VERDICTS, result_url
from app.prompts import load_prompt
from app.settings import get_config
from app.store import Store

log = logging.getLogger(__name__)
CLAIMS = "claims"
PROMPT = "02_near_match.md"
MAX_CHECKED = 2   # near-match calls per claim


@dataclass
class Tier2Result:
    hits: dict[str, dict[str, Any]] = field(default_factory=dict)        # claim_id -> verdict doc
    context: dict[str, list[Evidence]] = field(default_factory=dict)     # claim_id -> archived verdicts
    embeddings: dict[str, list[float]] = field(default_factory=dict)     # claim_id -> vector (to index later)

    def context_findings(self) -> AgentFindings | None:
        items = [e for ev in self.context.values() for e in ev]
        return AgentFindings(agent="cache_archive", evidence=items) if items else None


async def near_match(llm: LLM, claim: Claim, verdict: dict[str, Any], share_date: date) -> NearMatchResult:
    prompt = load_prompt(PROMPT)
    text = prompt.render(
        new_claim_en=claim.claim_en,
        new_claimed_date=claim.claimed_date.isoformat() if claim.claimed_date else "not stated",
        share_date=share_date.isoformat(), cached_claim_en=verdict.get("claim_en", ""),
        cached_event_date=verdict.get("event_date") or "unknown", cached_label=verdict.get("label", ""))
    return await llm.generate(stage="near_match", prompt=text, prompt_version=prompt.version,
                              schema=NearMatchResult, timeout_s=get_config().timeout("tier2"))


def _context_evidence(claim: Claim, verdict: dict[str, Any], n: int) -> Evidence:
    when = (verdict.get("created_at") or "")[:10]
    return Evidence(
        evidence_id=f"ca-{n}", agent="cache_archive", claim_id=claim.claim_id, url=result_url(verdict["verdict_id"]),
        publisher="Earlier check by this service", stance=Stance.CONTEXT,
        snippet_en=f"Previously checked on {when}: {verdict.get('label')}. {verdict.get('what_is_true_en', '')}"[:400],
    )


async def _one(store: Store, llm: LLM, claim: Claim, vector: list[float], share_date: date, out: Tier2Result,
               counter: list[int]) -> None:
    cache = get_config().limits["cache"]
    near = await store.find_nearest(CLAIMS, "embedding", vector, 5, {"status": "ACTIVE"})
    candidates = [(doc, d) for _, doc, d in near if d <= float(cache["tier2_weak_distance"])]
    now = datetime.now(UTC)
    for doc, distance in candidates[:MAX_CHECKED]:
        verdict = await store.get(VERDICTS, doc["verdict_id"])
        if not verdict or not _usable(verdict, now):
            continue
        decision = (await near_match(llm, claim, verdict, share_date)).decision
        log_event(log, "tier2 candidate", claim_id=claim.claim_id, distance=round(distance, 4), decision=decision)
        if decision == "SAME":
            out.hits[claim.claim_id] = verdict
            return
        if decision == "SAME_CLAIM_DIFFERENT_DATE":
            counter[0] += 1
            out.context.setdefault(claim.claim_id, []).append(_context_evidence(claim, verdict, counter[0]))


async def lookup(store: Store, llm: LLM, extraction: Extraction, share_date: date) -> Tier2Result:
    """Never raises: any failure means "no cache hit" and the full pipeline runs."""
    out = Tier2Result()
    if not extraction.claims:
        return out
    try:
        vectors = await llm.embed([c.claim_en for c in extraction.claims], timeout_s=get_config().timeout("tier2"))
        out.embeddings = {c.claim_id: v for c, v in zip(extraction.claims, vectors, strict=True)}
        counter = [0]
        await asyncio.gather(*(_one(store, llm, c, out.embeddings[c.claim_id], share_date, out, counter)
                               for c in extraction.claims))
    except (StageFailed, TimeoutError) as e:
        log_event(log, "tier2 skipped", logging.WARNING, reason=str(e)[:300])
    except Exception as e:  # noqa: BLE001  e.g. vector index missing: the cache must never fail a check
        log_event(log, "tier2 failed", logging.WARNING, reason=f"{type(e).__name__}: {str(e)[:300]}")
    return out


async def index(store: Store, verdict_id: str, claim_id: str, vector: list[float] | None) -> None:
    if vector:
        await store.set_vector(CLAIMS, f"{verdict_id}_{claim_id}", "embedding", vector)
