"""run_check(): the stage runner for one check. Deadlines, progress updates, final write.

Takes a CheckRequest and returns a CheckResult with no web-specific types, so a WhatsApp bot,
mobile app or B2B API can call it too.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from datetime import datetime

from app import quota
from app.agents import composer, extractor
from app.agents.tools import Tools, default_tools
from app.cache import tier1, tier2
from app.intake import links, media
from app.intake.hashing import extract_urls
from app.llm import LLM, StageFailed, get_llm
from app.models import AnswerText, CheckRequest, CheckResult, ClaimResult, Extraction, FetchedPost, Stage
from app.observability.calls import CheckLedger, ledger_var
from app.observability.logging import check_id_var, hash_uid, log_event, uid_hash_var
from app.observability.runs import write_check_run
from app.output import tts
from app.pipeline import investigate, stub
from app.pipeline.progress import CHECKS, now_iso, set_stage
from app.pipeline.results import VERDICTS, claim_result_from_doc, lang_key, persist_verdict
from app.settings import get_config, get_settings
from app.store import Store, get_store

log = logging.getLogger(__name__)
HARD_LIMIT_GRACE_S = 15
EXTRACTION_RETRY_MIN_LEFT_S = 50


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
    req: CheckRequest, *, store: Store, llm: LLM, cache_keys: list[str] | None = None, tools: Tools | None = None,
) -> CheckResult:
    check_id_var.set(req.check_id)
    uid_hash_var.set(hash_uid(req.uid))
    ledger = CheckLedger()
    ledger_var.set(ledger)
    started = time.monotonic()
    cfg = get_config()
    budget = cfg.total_budget(extractor.media_seconds(req))
    tools = tools or default_tools(store)
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
        # Stages cap themselves to the budget (investigate.Budget); this outer limit is a safety net.
        async with asyncio.timeout(budget + HARD_LIMIT_GRACE_S):
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
            try:
                extraction = await timed("extracting", extractor.extract(llm, req, fetched))
            except StageFailed as e:
                # Seen Oct 7: an image extraction (normally 3-8 s) stalled past 25 s even with a hedged
                # duplicate. With time left, one fresh attempt beats failing the user's check.
                left = budget - (time.monotonic() - started)
                if "timeout" not in e.reason or left < EXTRACTION_RETRY_MIN_LEFT_S:
                    raise
                log_event(log, "extraction retry", logging.WARNING, left_s=round(left, 1))
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
                deadline = investigate.Budget(started + budget)
                result = await _investigate(store, llm, tools, req, extraction, fetched, deadline, cache_keys or [],
                                            prompt_versions, timed)
    except (StageFailed, TimeoutError) as e:
        if extraction is None:
            return await _fail(store, req, "EXTRACTION_FAILED", str(e), ledger, timings, started)
        # Safety net hit after extraction: NOT_ENOUGH_EVIDENCE, said plainly, never cached.
        result = await _finish_degraded(store, req, extraction, prompt_versions)
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
    # Audio after DONE: the text answer shows at once; Gemini TTS takes 18-24 s per answer (Oct 7).
    # The Pub/Sub handler awaits this, so Cloud Run keeps CPU until the audio is stored.
    result = await timed("speaking", _speak(store, req, result))
    ledger.stage_latency_ms = timings
    asyncio.get_running_loop().create_task(write_check_run(req, result, ledger))
    return result


async def _speak(store: Store, req: CheckRequest, result: CheckResult) -> CheckResult:
    """Spoken answer in the content language for each claim that has none yet (cache hits reuse it)."""
    todo = [i for i, c in enumerate(result.claims) if not c.audio_url and c.answer.audio_script.strip()]
    if not todo or not tts_enabled():
        return result
    await store.set(CHECKS, req.check_id, {"result": {**result.model_dump(mode="json"), "audio_pending": True}},
                    merge=True)

    async def one(i: int) -> tuple[int, str | None]:
        c = result.claims[i]
        try:
            mp3 = await tts.synthesize(c.answer.audio_script, c.answer.language)
            await tts.store_audio(c.verdict_id, c.answer.language, mp3)
        except StageFailed as e:
            log_event(log, "tts failed", logging.WARNING, reason=str(e)[:300])
            return i, None
        url = tts.audio_url(c.verdict_id, c.answer.language)
        doc = await store.get(VERDICTS, c.verdict_id) or {}
        answers = dict(doc.get("answers") or {})
        base = c.answer.language.split("-")[0]
        key = next((k for k in answers if k.split("-")[0] == base), lang_key(c.answer.language))
        answers[key] = {**answers.get(key, c.answer.model_dump(mode="json")), "audio_url": url}
        await store.set(VERDICTS, c.verdict_id, {"answers": answers}, merge=True)
        return i, url

    urls = dict(await asyncio.gather(*(one(i) for i in todo)))
    claims = [c.model_copy(update={"audio_url": urls.get(i) or c.audio_url}) for i, c in enumerate(result.claims)]
    result = result.model_copy(update={"claims": claims, "audio_pending": False})
    await store.set(CHECKS, req.check_id, {"result": result.model_dump(mode="json")}, merge=True)
    return result


def tts_enabled() -> bool:
    """Off in LLM_MODE=fake (tests, offline UI) and when TTS_ENABLED=0."""
    return get_settings().llm_mode != "fake" and os.environ.get("TTS_ENABLED", "1") != "0"


async def _investigate(store, llm, tools, req, extraction, fetched, budget, cache_keys, prompt_versions, timed):
    # Stage 3: tier 2 cache. Claims that match an earlier verdict are answered from it; only the rest
    # go through the fan-out, panel and composer.
    t2 = await timed("tier2", tier2.lookup(store, llm, extraction, req.share_date))
    todo = [c for c in extraction.claims if c.claim_id not in t2.hits]
    by_claim: dict[str, ClaimResult] = {}
    for c in extraction.claims:
        if c.claim_id in t2.hits:
            by_claim[c.claim_id] = await _from_cache(store, llm, t2.hits[c.claim_id], extraction)
    degraded = False
    if todo:
        sub = extraction.model_copy(update={"claims": todo})
        extra = [f for f in [t2.context_findings()] if f]
        inv = await investigate.investigate(store, llm, tools, req, sub, fetched, budget, timed, extra)
        degraded = inv.degraded
        versions = prompt_versions | inv.prompt_versions
        cfg = get_config()
        models = {stage: cfg.model_for_stage(stage)["id"] for stage in ("extractor", *inv.prompt_versions)
                  if stage in cfg.models["stage_models"]}
        for claim in todo:
            d = inv.decisions[claim.claim_id]
            native, english = inv.answers[claim.claim_id]
            vid = await persist_verdict(
                store, check_id=req.check_id, claim=claim, verdict=d.verdict, outcome=d.outcome,
                evidence=inv.pack.evidence if inv.pack else [], answer=native, answer_en=english,
                prompt_versions=versions, model_versions=models, policy_reason=d.policy_reason,
                split_readings=d.split_readings,
            )
            if not degraded:
                await tier2.index(store, vid, claim.claim_id, t2.embeddings.get(claim.claim_id))
            by_claim[claim.claim_id] = claim_result_from_doc(await store.get(VERDICTS, vid),
                                                             extraction.content_language)
        await store.set(CHECKS, req.check_id, {
            "missing_lanes": inv.missing_lanes,
            "stage_errors": inv.stage_errors,  # debugging; not shown to users
            "source_assessment": inv.pack.source_assessment.model_dump(mode="json")
            if inv.pack and inv.pack.source_assessment else None,
        }, merge=True)
    claim_results = [by_claim[c.claim_id] for c in extraction.claims]
    if not degraded:
        vids = [c.verdict_id for c in claim_results]
        if cache_keys:
            await tier1.write(store, cache_keys, vids)
        await tier1.write_media(store, req.media, vids)
    return CheckResult(
        check_id=req.check_id, status="DONE", content_language=extraction.content_language,
        claims=claim_results, extra_claims_not_checked=extraction.extra_claims_not_checked,
        degraded=degraded, cache_tier_hit="T2" if not todo else "NONE",
    )


async def _from_cache(store, llm, verdict: dict, extraction) -> ClaimResult:
    """A cached verdict in this post's language; translated once and stored if it is missing."""
    lang = extraction.content_language
    answers = verdict.get("answers") or {}
    if not any(k.split("-")[0] == lang.split("-")[0] for k in answers):
        english = AnswerText.model_validate(answers.get(verdict.get("answer_en_key") or "en")
                                            or next(iter(answers.values())))
        try:
            native = await composer.translate(llm, english, lang, extraction.content_script)
            answers = {**answers, lang_key(lang): native.model_dump(mode="json")}
            await store.set(VERDICTS, verdict["verdict_id"], {"answers": answers}, merge=True)
            verdict = {**verdict, "answers": answers}
        except StageFailed as e:
            log_event(log, "translation failed", logging.WARNING, reason=str(e)[:300])
    return claim_result_from_doc(verdict, lang)


async def _finish_degraded(store, req, extraction, prompt_versions) -> CheckResult:
    claim_results = []
    for claim in extraction.claims:
        decision, native, english = investigate.degraded_answers([claim], extraction.content_language)[claim.claim_id]
        vid = await persist_verdict(
            store, check_id=req.check_id, claim=claim, verdict=decision.verdict, outcome=decision.outcome,
            evidence=[], answer=native, answer_en=english, prompt_versions=prompt_versions, model_versions={},
            policy_reason=decision.policy_reason, is_stub=True,
        )
        claim_results.append(claim_result_from_doc(await store.get(VERDICTS, vid), extraction.content_language))
    return CheckResult(check_id=req.check_id, status="DONE", content_language=extraction.content_language,
                       claims=claim_results, degraded=True)


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
        "error_detail": detail[:1000],  # for debugging; not returned by the API
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
