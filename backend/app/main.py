"""FastAPI app: public API (/v1) and the Pub/Sub push endpoint (/internal/pipeline)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import quota
from app.auth import User, current_user, verify_pubsub_push
from app.cache import tier1
from app.ids import ulid
from app.intake import media
from app.intake.hashing import extract_urls, text_key, url_key
from app.intake.validate import InvalidInput, UploadedFile, validate
from app.models import CheckRequest, CheckResult, MediaRef, Stage
from app.observability.logging import check_id_var, log_event, setup_logging
from app.pipeline.dispatch import dispatch
from app.pipeline.progress import CHECKS, PROGRESS, now_iso
from app.pipeline.results import VERDICTS, claim_result_from_doc, public_result
from app.settings import get_settings
from app.store import get_store

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(getattr(logging, get_settings().log_level, logging.INFO))
    from app.observability.bq_schemas import ensure_tables

    asyncio.get_running_loop().run_in_executor(None, ensure_tables)
    yield


app = FastAPI(title="Native-language fact checker", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    """Firebase Hosting rewrites /api/** to Cloud Run with the full path; the PWA calls /api/v1/..."""
    path = request.scope["path"]
    if path == "/api" or path.startswith("/api/"):
        request.scope["path"] = path[4:] or "/"
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "X-Firebase-AppCheck", "Content-Type"],
)


def error(status: int, code: str, message: str = "", **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error_code": code, "message": message or code, **extra})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error_code": "ERROR", "message": str(exc.detail)})


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "time": now_iso()}


# ---------- Checks ----------

def _input_types(text: str | None, url: str | None, kinds: list[str]) -> list[str]:
    types = (["text"] if text and text.strip() else []) + (["link"] if url else [])
    return types + sorted(set(kinds))


@app.post("/v1/checks")
async def create_check(
    user: User = Depends(current_user),
    text: str | None = Form(default=None),
    url: str | None = Form(default=None),
    client_lang: str = Form(default="en"),
    files: list[UploadFile] | None = File(default=None),
):
    store = get_store()
    uploads = [UploadedFile(f.filename or "file", await f.read(), f.content_type) for f in files or []]
    try:
        typed = validate(text, url, uploads)
    except InvalidInput as e:
        return error(400, e.error_code, e.message)
    # Fingerprint media before anything else: the tier 1 lookup needs the hashes, and files are
    # stored only on a cache miss.
    ingested = await media.fingerprint(typed) if typed else []

    url = (url or "").strip() or next(iter(extract_urls(text)), None)
    if ingested:
        # With media, only media keys identify the share: the same photo with a new caption is a hit.
        keys = [f"sha256:{i.sha256}" for i in ingested]
    else:
        keys = [k for k in [text_key(text) if text else None, url_key(url) if url else None] if k]

    allowed, status = await quota.consume(store, user)
    if not allowed:
        return error(429, "DAILY_LIMIT", "Daily limit reached", resets_at=status.resets_at.isoformat())

    check_id = ulid()
    check_id_var.set(check_id)
    now = datetime.now(UTC)
    base = {
        "check_id": check_id, "uid": user.uid, "created_at": now.isoformat(),
        "input_types": _input_types(text, url, [i.kind for i in ingested]), "source_url": url,
        "client_lang": client_lang, "media_trimmed": any(i.trimmed for i in ingested),
    }

    # Tier 1 cache (shared by all users). Cache hits count against quota (docs/08).
    if ingested:
        probe = [MediaRef(kind=i.kind, mime_type=i.mime_type, uri="", size_bytes=len(i.file.data), sha256=i.sha256,
                          phash=i.phash, frame_phashes=i.frame_phashes) for i in ingested]
        hit = await tier1.lookup_media(store, probe)
    else:
        hit = await tier1.lookup(store, keys)
    if hit:
        # The caption decides the answer language: the same video with a caption in another language
        # gets the cached verdict translated (once, then stored) and its own audio (acceptance case 3).
        from app.llm import get_llm
        from app.pipeline import reuse

        result = await reuse.tier1_answer(store, get_llm(), check_id, hit, text)
        await store.set(CHECKS, check_id, {
            **base, "status": "DONE", "stage": Stage.DONE.value, "stage_label_key": "stage.done",
            "progress": 100, "cache_tier_hit": "T1", "result": result.model_dump(mode="json"),
            "content_language": result.content_language,
            "verdict_ids": [c.verdict_id for c in result.claims],
        })
        await _history(user.uid, check_id, result)
        log_event(log, "tier1 hit", key=hit["key"], language=result.content_language)
        if reuse.needs_audio(result):
            await dispatch(check_id, task="speak")
        return {"check_id": check_id, "status": "DONE", "cache_tier_hit": "T1",
                "result": result.model_dump(mode="json")}

    if not await quota.consume_global(store):
        await quota.refund(store, user.uid)
        return error(503, "BUSY", "We are very busy right now. Please try again later.")

    stored = await media.store(check_id, ingested) if ingested else []
    req = CheckRequest(check_id=check_id, uid=user.uid, text=text, url=url, media=stored, client_lang=client_lang,
                       share_date=quota.local_date(now))
    await store.set(CHECKS, check_id, {
        **base, "status": "RUNNING", "stage": Stage.RECEIVED.value, "stage_label_key": "stage.received",
        "progress": PROGRESS[Stage.RECEIVED], "cache_tier_hit": "NONE", "degraded": False,
        "request": req.model_dump(mode="json"), "cache_keys": keys, "agents": {},
    })
    await dispatch(check_id)
    return JSONResponse(status_code=202, content={"check_id": check_id, "status": "RUNNING"})


async def _history(uid: str, check_id: str, result: CheckResult) -> None:
    first = result.claims[0] if result.claims else None
    await get_store().set(f"users/{uid}/history", check_id, {
        "check_id": check_id, "created_at": now_iso(),
        "headline": first.answer.headline if first else (result.non_checkable_message or ""),
        "label": first.label.value if first else "NOT_CHECKABLE",
        "labels": [c.label.value for c in result.claims],
        "content_language": result.content_language, "status": result.status,
    })


async def _owned_check(check_id: str, user: User) -> dict:
    doc = await get_store().get(CHECKS, check_id)
    if not doc or doc.get("uid") != user.uid:
        raise HTTPException(404, detail={"error_code": "NOT_FOUND"})
    return doc


@app.get("/v1/checks/{check_id}")
async def get_check(check_id: str, user: User = Depends(current_user)) -> dict:
    doc = await _owned_check(check_id, user)
    public = {k: v for k, v in doc.items() if k not in ("request", "cache_keys", "uid", "error_detail", "stage_errors")}
    return public


class Feedback(BaseModel):
    helpful: bool
    reason: str | None = None


@app.post("/v1/checks/{check_id}/feedback", status_code=204)
async def feedback(check_id: str, body: Feedback, user: User = Depends(current_user)) -> Response:
    await _owned_check(check_id, user)
    await get_store().set("feedback", f"{check_id}_{user.uid}", {
        "check_id": check_id, "helpful": body.helpful, "reason": (body.reason or "")[:500],
        "created_at": now_iso(),
    })
    return Response(status_code=204)


# ---------- Me ----------

@app.get("/v1/me")
async def me(user: User = Depends(current_user)) -> dict:
    doc = await get_store().get("users", user.uid) or {}
    return {"uid": user.uid, "email": user.email, "consent_at": doc.get("consent_at"),
            "ui_language": doc.get("ui_language"), "is_judge": user.is_judge}


@app.get("/v1/me/quota")
async def my_quota(user: User = Depends(current_user)) -> dict:
    return (await quota.get_quota(get_store(), user)).as_dict()


@app.get("/v1/me/history")
async def my_history(cursor: str | None = None, user: User = Depends(current_user)) -> dict:
    items = await get_store().list_recent(f"users/{user.uid}/history", "created_at", 20, start_after=cursor)
    return {"items": [v for _, v in items], "next_cursor": items[-1][0] if len(items) == 20 else None}


class FcmToken(BaseModel):
    token: str


@app.post("/v1/me/fcm-token", status_code=204)
async def fcm_token(body: FcmToken, user: User = Depends(current_user)) -> Response:
    store = get_store()
    doc = await store.get("users", user.uid) or {}
    tokens = [t for t in doc.get("fcm_tokens") or [] if t != body.token][-4:] + [body.token]
    await store.set("users", user.uid, {"fcm_tokens": tokens}, merge=True)
    return Response(status_code=204)


class Consent(BaseModel):
    ui_language: str | None = None


@app.post("/v1/me/consent", status_code=204)
async def consent(body: Consent | None = None, user: User = Depends(current_user)) -> Response:
    store = get_store()
    existing = await store.get("users", user.uid)
    data = {"consent_at": now_iso(), "email": user.email, "display_name": user.name}
    if body and body.ui_language:
        data["ui_language"] = body.ui_language
    if not existing:
        data |= {"created_at": now_iso(), "role": "JUDGE" if user.is_judge else "USER", "fcm_tokens": []}
    await store.set("users", user.uid, data, merge=True)
    return Response(status_code=204)


@app.delete("/v1/me", status_code=204)
async def delete_me(user: User = Depends(current_user)) -> Response:
    """Remove the user doc, history and today's usage. Shared verdicts hold no personal data."""
    store = get_store()
    col = f"users/{user.uid}/history"
    while items := await store.list_recent(col, "created_at", 100):
        for doc_id, _ in items:
            await store.delete(col, doc_id)
    await store.delete("users", user.uid)
    await store.delete(quota.USAGE, quota.usage_doc_id(user.uid))
    return Response(status_code=204)


# ---------- Public result page ----------

_ip_hits: dict[str, list[float]] = defaultdict(list)
RESULTS_PER_MINUTE = 60


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _ip_hits[ip] if now - t < 60]
    hits.append(now)
    _ip_hits[ip] = hits
    return len(hits) > RESULTS_PER_MINUTE


@app.get("/v1/results/{verdict_id}")
async def get_result(verdict_id: str, request: Request, lang: str | None = None):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0]
    if _rate_limited(ip.strip()):
        return error(429, "RATE_LIMITED")
    doc = await get_store().get(VERDICTS, verdict_id)
    if not doc:
        return error(404, "NOT_FOUND")
    return public_result(doc, lang)


@app.get("/v1/results/{verdict_id}/audio")
async def get_result_audio(verdict_id: str, request: Request, lang: str = "en"):
    """The spoken answer (MP3). Served through the API so the outputs bucket stays private."""
    from app.output import tts

    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0]
    if _rate_limited(ip.strip()):
        return error(429, "RATE_LIMITED")
    data = await tts.read_audio(verdict_id, lang)
    if data is None:
        return error(404, "NOT_FOUND")
    return Response(content=data, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/v1/results/{verdict_id}/card")
async def get_result_card(verdict_id: str, request: Request, lang: str = "en"):
    """The correction card (PNG), drawn on first request from the stored verdict and kept in the outputs
    bucket. Through the API so the bucket stays private."""
    from app.output import card

    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0]
    if _rate_limited(ip.strip()):
        return error(429, "RATE_LIMITED")
    data = await card.read_card(verdict_id, lang)
    if data is None:
        doc = await get_store().get(VERDICTS, verdict_id)
        if not doc or not doc.get("answers"):
            return error(404, "NOT_FOUND")
        data = await asyncio.to_thread(card.render, claim_result_from_doc(doc, lang))
        await card.store_card(verdict_id, lang, data)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


# ---------- Pipeline (Pub/Sub push) ----------

@app.post("/internal/pipeline", status_code=204, dependencies=[Depends(verify_pubsub_push)])
async def pipeline(request: Request) -> Response:
    from app.pipeline.runner import run_check_by_id

    envelope = await request.json()
    try:
        payload = json.loads(base64.b64decode(envelope["message"]["data"]))
        check_id = payload["check_id"]
    except (KeyError, ValueError, TypeError):
        # Malformed message: ack so Pub/Sub does not retry forever.
        log_event(log, "bad pubsub envelope", logging.WARNING)
        return Response(status_code=204)
    check_id_var.set(check_id)
    if payload.get("task") == "speak":
        from app.pipeline.reuse import speak_check

        await speak_check(get_store(), check_id)
    else:
        await run_check_by_id(check_id)
    return Response(status_code=204)
