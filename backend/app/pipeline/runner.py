"""run_check(): the stage runner for one check. Deadlines, progress updates, final write.

Takes a CheckRequest and returns a CheckResult with no web-specific types, so a WhatsApp bot,
mobile app or B2B API can call it too.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from datetime import datetime

from app import quota
from app.agents import extractor
from app.cache import tier1
from app.intake import links, media
from app.intake.hashing import extract_urls
from app.llm import LLM, StageFailed, get_llm
from app.models import CheckRequest, CheckResult, Extraction, FetchedPost, Stage
from app.observability.calls import CheckLedger, ledger_var
from app.observability.logging import check_id_var, hash_uid, log_event, uid_hash_var
from app.observability.runs import write_check_run
from app.pipeline import panel, stub
from app.pipeline.progress import CHECKS, now_iso, set_stage
from app.pipeline.results import VERDICTS, claim_result_from_doc, persist_verdict
from app.settings import get_config
from app.store import Store, get_store

log = logging.getLogger(__name__)


async def run_check_by_id(check_id: str, store: Store | None = None, llm: LLM | None = None) -> CheckResult | None:
    """Entry point for /internal/pipeline and inline mode. Idempotent."""
    store = store or get_store()
    doc = await store.get(CHECKS, check_id)
    if not doc:
        log_event(log, "check not found", logging.WARNING, check_id=check_id)
        return None
    if doc.get("status") in ("DONE", "FAILED", "LIMIT"):
        return CheckResult.model_validate(doc["result"]) if doc.get("result") else None
    req = CheckRequest.model_validate(doc["request"])
    return await run_check(req, store=store, llm=llm or get_llm(), cache_keys=doc.get("cache_keys") or [])


async def run_check(
    req: CheckRequest, *, store: Store, llm: LLM, cache_keys: list[str] | None = None
) -> CheckResult:
    check_id_var.set(req.check_id)
    uid_hash_var.set(hash_uid(req.uid))
    ledger = CheckLedger()
    ledger_var.set(ledger)
    started = time.monotonic()
    cfg = get_config()
    budget = cfg.total_budget(extractor.media_seconds(req))
    prompt_versions: dict[str, str] = {}
    timings: dict[str, int] = {}

    async def timed(stage: str, coro):
        t0 = time.monotonic()
        try:
            return await coro
        finally:
            timings[stage] = int((time.monotonic() - t0) * 1000)

    extraction: Extraction | None = None
    fetched: FetchedPost | None = None
    try:
        async with asyncio.timeout(budget):
            if req.url:
                await set_stage(store, req.check_id, Stage.FETCHING_LINK)
                fetched = await timed("fetching_link", links.fetch(
                    req.url, store_image=functools.partial(media.store_link_image, req.check_id)))
                await store.set(CHECKS, req.check_id, {
                    "platform": fetched.platform, "fetch_method": fetched.fetch_method,
                    "author_handle": fetched.author_handle, "fetched_at": now_iso(),
                    "published_at": fetched.published_at.isoformat() if fetched.published_at else None,
                }, merge=True)
                if fetched.fetch_method == "failed" and not _has_own_content(req):
                    return await _finish_unreadable_link(store, req, ledger, timings, started)
            await set_stage(store, req.check_id, Stage.EXTRACTING)
            extraction = await timed("extracting", extractor.extract(llm, req, fetched))
            prompt_versions["extractor"] = extractor.load_prompt(extractor.PROMPT).version
            await store.set(CHECKS, req.check_id, {
                "content_language": extraction.content_language,
                "extraction_summary_en": extraction.summary_en,
                "claims_preview": [c.claim_original for c in extraction.claims],
            }, merge=True)

            if not extraction.checkable:
                result = await _finish_not_checkable(store, req, extraction, cache_keys or [])
            else:
                result = await _investigate(store, req, extraction, cache_keys or [], prompt_versions, timed)
    except (StageFailed, TimeoutError) as e:
        if extraction is None:
            return await _fail(store, req, "EXTRACTION_FAILED", str(e), ledger, timings, started)
        # Whole budget exceeded after extraction: NOT_ENOUGH_EVIDENCE with what we have.
        result = await _investigate(store, req, extraction, [], prompt_versions, timed, degraded=True)
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline crashed")
        return await _fail(store, req, "INTERNAL", repr(e), ledger, timings, started)

    # The link had a photo or video we could not get, and the user did not attach one.
    result.media_missing_prompt = bool(fetched and fetched.media_missing and not req.media)
    result.latency_ms = int((time.monotonic() - started) * 1000)
    await store.set(CHECKS, req.check_id, {
        "status": "DONE", "result": result.model_dump(mode="json"), "latency_ms": result.latency_ms,
        "verdict_ids": [c.verdict_id for c in result.claims], "degraded": result.degraded,
    }, merge=True)
    await set_stage(store, req.check_id, Stage.DONE)
    await _write_history(store, req, result)
    ledger.stage_latency_ms = timings
    asyncio.get_running_loop().create_task(write_check_run(req, result, ledger))
    return result


async def _investigate(store, req, extraction, cache_keys, prompt_versions, timed, degraded=False):
    # Stages 3 to 7 (tier 2 cache, fan-out, packager, panel, composer) are stubbed for Day 1.
    claim_results = []
    for claim in extraction.claims:
        judged = stub.stub_judge(claim)
        decision = panel.merge(judged, None, evidence=[])
        native = stub.stub_answer(claim, decision.verdict, extraction.content_language)
        english = stub.stub_answer(claim, decision.verdict, "en")
        vid = await persist_verdict(
            store, check_id=req.check_id, claim=claim, verdict=decision.verdict,
            outcome=decision.outcome,
            evidence=[], answer=native, answer_en=english, prompt_versions=prompt_versions,
            model_versions={"extractor": get_config().model_for_stage("extractor")["id"]},
            policy_reason=decision.policy_reason, is_stub=True,
        )
        claim_results.append(claim_result_from_doc(await store.get(VERDICTS, vid), extraction.content_language))
    await set_stage(store, req.check_id, Stage.COMPOSING)
    if not degraded:
        vids = [c.verdict_id for c in claim_results]
        if cache_keys:
            await tier1.write(store, cache_keys, vids)
        await tier1.write_media(store, req.media, vids)
    return CheckResult(
        check_id=req.check_id, status="DONE", content_language=extraction.content_language,
        claims=claim_results, extra_claims_not_checked=extraction.extra_claims_not_checked,
        degraded=degraded,
    )


async def _finish_not_checkable(store, req, extraction, cache_keys) -> CheckResult:
    nct = extraction.non_checkable_type.value if extraction.non_checkable_type else "OTHER"
    message = stub.non_checkable_message(nct, extraction.content_language)
    non_checkable = {"type": nct, "message": message, "content_language": extraction.content_language}
    if cache_keys:
        await tier1.write(store, cache_keys, [], non_checkable=non_checkable)
    await tier1.write_media(store, req.media, [], non_checkable=non_checkable)
    return CheckResult(
        check_id=req.check_id, status="DONE", content_language=extraction.content_language,
        non_checkable_type=nct, non_checkable_message=message,
    )


def _has_own_content(req: CheckRequest) -> bool:
    """Media, or text beyond the link itself (WhatsApp often shares a link as the whole text)."""
    text = req.text or ""
    for u in extract_urls(text):
        text = text.replace(u, "")
    return bool(req.media) or bool(text.strip())


async def _finish_unreadable_link(store, req, ledger, timings, started) -> CheckResult:
    """Nothing to check: ask for a screenshot. A total fetch failure does not use up quota (docs/03)."""
    result = CheckResult(check_id=req.check_id, status="DONE", media_missing_prompt=True,
                         latency_ms=int((time.monotonic() - started) * 1000))
    await store.set(CHECKS, req.check_id, {
        "status": "DONE", "result": result.model_dump(mode="json"), "latency_ms": result.latency_ms,
        "error_code": "LINK_UNREADABLE",
    }, merge=True)
    await set_stage(store, req.check_id, Stage.DONE)
    doc = await store.get(CHECKS, req.check_id) or {}
    created = datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None
    await quota.refund(store, req.uid, created)
    ledger.stage_latency_ms = timings
    asyncio.get_running_loop().create_task(write_check_run(req, result, ledger, error_code="LINK_UNREADABLE"))
    return result


async def _fail(store, req, code, detail, ledger, timings, started) -> CheckResult:
    log_event(log, "check failed", logging.ERROR, error_code=code, detail=detail[:500])
    result = CheckResult(check_id=req.check_id, status="FAILED",
                         latency_ms=int((time.monotonic() - started) * 1000))
    await store.set(CHECKS, req.check_id, {
        "status": "FAILED", "error_code": code, "result": result.model_dump(mode="json"),
    }, merge=True)
    await set_stage(store, req.check_id, Stage.FAILED)
    # Failed checks do not count against the quota.
    doc = await store.get(CHECKS, req.check_id) or {}
    created = datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None
    await quota.refund(store, req.uid, created)
    ledger.stage_latency_ms = timings
    asyncio.get_running_loop().create_task(write_check_run(req, result, ledger, error_code=code))
    return result


async def _write_history(store: Store, req: CheckRequest, result: CheckResult) -> None:
    first = result.claims[0] if result.claims else None
    await store.set(f"users/{req.uid}/history", req.check_id, {
        "check_id": req.check_id,
        "created_at": now_iso(),
        "headline": first.answer.headline if first else (result.non_checkable_message or ""),
        "label": first.label.value if first else "NOT_CHECKABLE",
        "labels": [c.label.value for c in result.claims],
        "content_language": result.content_language,
        "status": result.status,
    })
