"""Structured model calls on Vertex AI Gemini.

Every call: model by stage key from config/models.yaml, Pydantic response schema,
deadline, one retry with the validation error appended, and a ModelCall record.
LLM_MODE=fake swaps in FakeLLM (recorded fixtures) so tests make no paid calls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.models import GroundedSource, GroundedText
from app.observability.calls import ModelCall, current_ledger, model_cost
from app.observability.logging import check_id_var, log_event
from app.settings import get_config, get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class StageFailed(Exception):
    """A model stage could not produce valid output (after retry) or timed out."""

    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


@dataclass
class MediaPart:
    mime_type: str
    uri: str | None = None          # gs:// or https:// (YouTube)
    data: bytes | None = None       # inline bytes (small images)
    low_resolution: bool = False
    end_offset_s: float | None = None


class LLM(Protocol):
    async def generate(
        self,
        *,
        stage: str,
        prompt: str,
        prompt_version: str,
        schema: type[T],
        media: list[MediaPart] | None = None,
        timeout_s: float,
        model_key: str | None = None,
    ) -> T: ...

    async def search(self, *, stage: str, prompt: str, prompt_version: str, timeout_s: float) -> GroundedText: ...

    async def embed(self, texts: list[str], *, timeout_s: float) -> list[list[float]]: ...


def _thinking_config(model: dict[str, Any]):
    """Gemini 3 models take `thinking: low|medium|high`; 2.5 models take `thinking_budget` (tokens)."""
    from google.genai import types

    if model.get("thinking_budget") is not None:
        return types.ThinkingConfig(thinking_budget=int(model["thinking_budget"]))
    if model.get("thinking"):
        return types.ThinkingConfig(thinking_level=str(model["thinking"]).upper())
    return None


class GeminiLLM:
    def __init__(self) -> None:
        from google import genai

        s = get_settings()
        cfg = get_config().models
        location = s.vertex_location or cfg["vertex"]["location"]
        self._client = genai.Client(vertexai=True, project=s.gcp_project, location=location)

    def _parts(self, prompt: str, media: list[MediaPart] | None) -> list[Any]:
        from google.genai import types

        parts: list[Any] = []
        for m in media or []:
            if m.data is not None:
                part = types.Part.from_bytes(data=m.data, mime_type=m.mime_type)
            else:
                part = types.Part(file_data=types.FileData(file_uri=m.uri, mime_type=m.mime_type))
                if m.end_offset_s is not None:
                    part.video_metadata = types.VideoMetadata(end_offset=f"{int(m.end_offset_s)}s")
            parts.append(part)
        parts.append(types.Part.from_text(text=prompt))
        return parts

    async def generate(
        self,
        *,
        stage: str,
        prompt: str,
        prompt_version: str,
        schema: type[T],
        media: list[MediaPart] | None = None,
        timeout_s: float,
        model_key: str | None = None,
    ) -> T:
        from google.genai import types

        cfg = get_config()
        model = cfg.models["models"][model_key] if model_key else cfg.model_for_stage(stage)
        key = model_key or model["key"]
        low_res = any(m.low_resolution for m in media or [])
        priority = priority_requested(stage)

        def gen_cfg(m: dict[str, Any]):
            return types.GenerateContentConfig(
                http_options=types.HttpOptions(headers=PRIORITY_HEADERS) if priority else None,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
                thinking_config=_thinking_config(m),
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if low_res else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
        text = prompt
        last_error = ""
        for attempt in range(2):
            started = time.monotonic()
            call = ModelCall(
                check_id=check_id_var.get(), stage=stage, model_id=model["id"],
                prompt_version=prompt_version, retry=attempt > 0,
            )
            contents = self._parts(text, media)
            try:
                resp = await _with_fallback(
                    lambda m, t, c=contents, call=call: _retry_transient(lambda: _hedged(
                        lambda: self._client.aio.models.generate_content(model=m["id"], contents=c, config=gen_cfg(m)),
                        t, m.get("hedge_after_s"), stage), budget_s=t, call=call),
                    model, timeout_s, call)
            except TimeoutError as e:
                call.success = False
                call.error_code = error_code(e)
                call.latency_ms = int((time.monotonic() - started) * 1000)
                _record(call)
                raise StageFailed(stage, f"timeout after {timeout_s}s") from e
            except Exception as e:  # noqa: BLE001  API errors (5xx, 429, 400) fail the stage, not the check
                call.success = False
                call.error_code = error_code(e)
                call.latency_ms = int((time.monotonic() - started) * 1000)
                _record(call)
                raise StageFailed(stage, f"model API error: {type(e).__name__}: {str(e)[:200]}") from e
            call.latency_ms = int((time.monotonic() - started) * 1000)
            usage = resp.usage_metadata
            if usage:
                call.input_tokens = usage.prompt_token_count or 0
                call.output_tokens = usage.candidates_token_count or 0
                call.thinking_tokens = usage.thoughts_token_count or 0
                call.priority = "PRIORITY" in str(getattr(usage, "traffic_type", "") or "")
            call.cost_usd = model_cost(key, call.input_tokens, call.output_tokens, call.thinking_tokens,
                                       priority=call.priority)
            try:
                result = schema.model_validate_json(resp.text or "")
                _record(call)
                return result
            except ValidationError as e:
                call.success = False
                call.error_code = "VALIDATION"
                _record(call)
                last_error = str(e)[:2000]
                text = (
                    f"{prompt}\n\nYour previous answer failed validation with this error. "
                    f"Return corrected JSON only.\n{last_error}"
                )
        raise StageFailed(stage, f"invalid output after retry: {last_error[:300]}")

    async def embed(self, texts: list[str], *, timeout_s: float) -> list[list[float]]:
        """Embeddings for tier 2 (config/models.yaml `embedding`), one vector per text."""
        from google.genai import types

        m = get_config().models["models"]["embedding"]
        call = ModelCall(check_id=check_id_var.get(), stage="embedding", model_id=m["id"], prompt_version="-")
        started = time.monotonic()
        try:
            resp = await _retry_transient(lambda: _hedged(lambda: self._client.aio.models.embed_content(
                model=m["id"], contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=int(m["dims"]), task_type="SEMANTIC_SIMILARITY"),
            ), timeout_s, m.get("hedge_after_s"), "embedding"), call=call)
        except Exception as e:  # noqa: BLE001  tier 2 is an optimisation; never fail the check for it
            call.success = False
            call.error_code = error_code(e)
            call.latency_ms = int((time.monotonic() - started) * 1000)
            _record(call)
            raise StageFailed("embedding", f"{type(e).__name__}: {str(e)[:200]}") from e
        call.latency_ms = int((time.monotonic() - started) * 1000)
        call.input_tokens = sum(len(t) // 4 for t in texts)  # the API does not report tokens; estimate
        call.cost_usd = model_cost("embedding", call.input_tokens, 0)
        _record(call)
        return [list(e.values) for e in resp.embeddings]

    async def search(self, *, stage: str, prompt: str, prompt_version: str, timeout_s: float) -> GroundedText:
        """Grounding with Google Search, free-text answer. JSON output mode would drop the grounding
        sources, so structuring happens in a separate call that cites sources by number."""
        from google.genai import types

        model = get_config().model_for_stage(stage)
        def gen_cfg(m: dict[str, Any]):
            return types.GenerateContentConfig(
                temperature=0.2, thinking_config=_thinking_config(m),
                tools=[types.Tool(google_search=types.GoogleSearch())],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
        call = ModelCall(check_id=check_id_var.get(), stage=stage, model_id=model["id"], prompt_version=prompt_version)
        started = time.monotonic()
        try:
            # Measured Oct 5: identical searches take 8-9 s or 35-55 s (server side), so hedge early.
            # A hedge duplicates the grounding queries (billed per query); watch the cost.
            resp = await _with_fallback(lambda m, t: _retry_transient(lambda: _hedged(
                lambda: self._client.aio.models.generate_content(model=m["id"], contents=prompt, config=gen_cfg(m)),
                t, m.get("search_hedge_after_s"), stage), budget_s=t, call=call), model, timeout_s, call)
        except TimeoutError as e:
            call.success = False
            call.error_code = error_code(e)
            call.latency_ms = int((time.monotonic() - started) * 1000)
            _record(call)
            raise StageFailed(stage, f"timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            call.success = False
            call.error_code = error_code(e)
            call.latency_ms = int((time.monotonic() - started) * 1000)
            _record(call)
            raise StageFailed(stage, f"model API error: {type(e).__name__}: {str(e)[:200]}") from e
        call.latency_ms = int((time.monotonic() - started) * 1000)
        usage = resp.usage_metadata
        if usage:
            call.input_tokens = usage.prompt_token_count or 0
            call.output_tokens = usage.candidates_token_count or 0
            call.thinking_tokens = usage.thoughts_token_count or 0
        call.cost_usd = model_cost(model["key"], call.input_tokens, call.output_tokens, call.thinking_tokens)
        out = await grounded_text(resp)
        call.grounding_queries = out.queries
        current_ledger().grounding_queries += out.queries
        _record(call)
        return out


def _retryable(e: BaseException) -> bool:
    """Transient Vertex errors worth one quick retry: 5xx and 429 (seen Oct 5: a judge call failed in 1 s
    with an API error; the identical request then succeeded three times)."""
    from google.genai import errors

    if isinstance(e, errors.ServerError):
        return True
    return isinstance(e, errors.ClientError) and getattr(e, "code", None) == 429


RETRY_DELAYS_S = (1.0, 3.0, 6.0)


FALLBACK_MIN_S = 5.0
# Vertex Priority PayGo (config/models.yaml `priority`): a per-request header, no other setup.
PRIORITY_HEADERS = {"X-Vertex-AI-LLM-Shared-Request-Type": "priority"}


def priority_requested(stage: str) -> bool:
    p = get_config().models.get("priority") or {}
    return bool(p.get("enabled")) and stage in (p.get("stages") or [])


def fallback_model(model: dict[str, Any]) -> dict[str, Any] | None:
    """The alias's fallback as a model entry: its own id and thinking settings, the alias's hedges and prices."""
    fb = model.get("fallback")
    if not fb:
        return None
    base = {k: v for k, v in model.items() if k not in ("fallback", "id", "thinking_budget", "thinking")}
    return {**base, **fb}


async def _with_fallback(run: Callable[[dict[str, Any], float], Awaitable[Any]], model: dict[str, Any],
                         timeout_s: float, call: ModelCall) -> Any:
    """run(model, timeout) on the configured model; after its retries, a final 429 or 5xx tries the alias's
    fallback once with what is left of the budget (Vertex dynamic shared quota is per model, Oct 9).
    Timeouts do not fall back: the budget is gone."""
    started = time.monotonic()
    try:
        return await run(model, timeout_s)
    except TimeoutError:
        raise
    except Exception as e:  # noqa: BLE001
        fb = fallback_model(model)
        left = timeout_s - (time.monotonic() - started)
        if fb is None or not _retryable(e) or left < FALLBACK_MIN_S:
            raise
        log_event(log, "using fallback model", logging.WARNING, stage=call.stage, primary=model["id"],
                  fallback=fb["id"], code=getattr(e, "code", None), left_s=round(left, 1))
        call.model_id, call.fallback = fb["id"], True
        return await run(fb, left)


def error_code(e: BaseException) -> str:
    """Short code for model_calls.error_code: the HTTP status for API errors, else the kind of failure."""
    if isinstance(e, TimeoutError):
        return "TIMEOUT"
    if isinstance(e, ValidationError):
        return "VALIDATION"
    code = getattr(e, "code", None)
    return str(code) if code else type(e).__name__


async def _retry_transient(make: Callable[[], Awaitable[Any]], budget_s: float | None = None,
                           call: ModelCall | None = None) -> Any:
    """Retry transient Vertex errors (5xx, 429) with growing, jittered backoff while the budget allows.
    One quick retry was not enough for 429 RESOURCE_EXHAUSTED under load (Oct 8: three checks in parallel
    lost their web search and composer, so the check was degraded and not cached)."""
    import random

    started = time.monotonic()
    for delay in (*RETRY_DELAYS_S, None):
        try:
            return await make()
        except TimeoutError:
            raise
        except Exception as e:  # noqa: BLE001
            if call is not None and _retryable(e):
                if getattr(e, "code", None) == 429:
                    call.rate_limited += 1
                else:
                    call.server_errors += 1
            if delay is None or not _retryable(e):
                raise
            wait = delay * (0.75 + random.random() / 2)
            if budget_s is not None and time.monotonic() - started + wait > budget_s * 0.7:
                raise
            log_event(log, "retrying transient model error", logging.WARNING, error=type(e).__name__,
                      code=getattr(e, "code", None), wait_s=round(wait, 1))
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


async def _hedged(make_call: Callable[[], Awaitable[Any]], timeout_s: float, hedge_after_s: float | None,
                  stage: str) -> Any:
    """Tail-latency guard. If the call has not returned after hedge_after_s (about the model's p90),
    start an identical second call and take whichever finishes first. Vertex occasionally stalls a
    call for 20+ s that normally takes 5; a duplicate usually lands in normal time.
    Raises TimeoutError when neither finishes within timeout_s."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    first = asyncio.ensure_future(make_call())
    tasks = {first}
    try:
        if hedge_after_s and hedge_after_s < timeout_s * 0.8:
            done, _ = await asyncio.wait(tasks, timeout=hedge_after_s)
            if not done:
                log_event(log, "hedging slow model call", stage=stage, after_s=hedge_after_s)
                tasks.add(asyncio.ensure_future(make_call()))
        while tasks:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            done, _ = await asyncio.wait(tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise TimeoutError
            for t in done:
                tasks.discard(t)
                if t.exception() is None:
                    return t.result()
                if not tasks:
                    raise t.exception()  # type: ignore[misc]
        raise TimeoutError
    finally:
        for t in tasks:
            t.cancel()


_REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"


async def _resolve(uris: list[str]) -> dict[str, str | None]:
    """Google's grounding redirect links -> real page URLs (one 302 hop each, in parallel)."""
    import httpx

    async def one(client: httpx.AsyncClient, uri: str) -> tuple[str, str | None]:
        if not uri.startswith(_REDIRECT):
            return uri, uri
        try:
            r = await client.get(uri, follow_redirects=False)
            return uri, r.headers.get("location") if r.is_redirect else None
        except httpx.HTTPError:
            return uri, None

    async with httpx.AsyncClient(timeout=3.0) as client:
        return dict(await asyncio.gather(*(one(client, u) for u in dict.fromkeys(uris))))


async def grounded_text(resp: Any) -> GroundedText:
    """Text with [n] after each segment Google attributes to source n, plus the resolved sources.
    Segment offsets are UTF-8 byte offsets."""
    text = resp.text or ""
    gm = resp.candidates[0].grounding_metadata if resp.candidates else None
    if not gm or not gm.grounding_chunks:
        return GroundedText(text=text, queries=len(gm.web_search_queries or []) if gm else 0)
    uris = [c.web.uri if c.web else "" for c in gm.grounding_chunks]
    real = await _resolve([u for u in uris if u])
    sources = [GroundedSource(n=i + 1, url=real[u], domain=c.web.title if c.web else None)
               for i, (u, c) in enumerate(zip(uris, gm.grounding_chunks, strict=True)) if u and real.get(u)]
    known = {s.n for s in sources}
    raw = text.encode("utf-8")
    inserts: dict[int, list[int]] = {}
    for sp in gm.grounding_supports or []:
        ns = [i + 1 for i in sp.grounding_chunk_indices or [] if i + 1 in known]
        if ns and sp.segment and sp.segment.end_index is not None:
            inserts.setdefault(sp.segment.end_index, []).extend(ns)
    for end in sorted(inserts, reverse=True):
        marks = "".join(f" [{n}]" for n in dict.fromkeys(inserts[end]))
        raw = raw[:end] + marks.encode() + raw[end:]
    return GroundedText(text=raw.decode("utf-8", errors="replace"), sources=sources,
                        queries=len(gm.web_search_queries or []))


def _record(call: ModelCall) -> None:
    current_ledger().calls.append(call)
    log_event(log, "model_call", **call.row())


Fixture = BaseModel | dict | Callable[[str], BaseModel | dict]


class FakeLLM:
    """Returns recorded outputs per stage. Used by tests and LLM_MODE=fake local runs."""

    def __init__(self, fixtures: dict[str, Fixture] | None = None) -> None:
        self.fixtures: dict[str, Fixture] = dict(fixtures or {})
        self.prompts: dict[str, list[str]] = {}

    async def generate(
        self,
        *,
        stage: str,
        prompt: str,
        prompt_version: str,
        schema: type[T],
        media: list[MediaPart] | None = None,
        timeout_s: float,
        model_key: str | None = None,
    ) -> T:
        self.prompts.setdefault(stage, []).append(prompt)
        if stage not in self.fixtures:
            raise StageFailed(stage, "no fixture")
        fx = self.fixtures[stage]
        value = fx(prompt) if callable(fx) and not isinstance(fx, BaseModel) else fx
        if isinstance(value, Exception):
            raise value
        model_id = get_config().model_for_stage(stage)["id"] if model_key is None else model_key
        _record(ModelCall(check_id=check_id_var.get(), stage=stage, model_id=model_id,
                          prompt_version=prompt_version))
        if isinstance(value, BaseModel):
            return schema.model_validate(value.model_dump())
        return schema.model_validate(json.loads(json.dumps(value, default=str)))

    async def embed(self, texts: list[str], *, timeout_s: float) -> list[list[float]]:
        """Deterministic bag-of-words vectors: identical or reworded texts land close, unrelated ones far."""
        dims = int(get_config().models["models"]["embedding"]["dims"])
        out = []
        for t in texts:
            v = [0.0] * dims
            for w in re.findall(r"\w+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0
            out.append(v)
        return out

    async def search(self, *, stage: str, prompt: str, prompt_version: str, timeout_s: float) -> GroundedText:
        self.prompts.setdefault(stage, []).append(prompt)
        if stage not in self.fixtures:
            raise StageFailed(stage, "no fixture")
        fx = self.fixtures[stage]
        value = fx(prompt) if callable(fx) and not isinstance(fx, BaseModel) else fx
        if isinstance(value, Exception):
            raise value
        _record(ModelCall(check_id=check_id_var.get(), stage=stage,
                          model_id=get_config().model_for_stage(stage)["id"], prompt_version=prompt_version))
        return GroundedText.model_validate(value.model_dump() if isinstance(value, BaseModel) else value)


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        if get_settings().llm_mode == "fake":
            from app.fixtures import demo_fixtures

            _llm = FakeLLM(demo_fixtures())
        else:
            _llm = GeminiLLM()
    return _llm


def set_llm(llm: LLM | None) -> None:
    global _llm
    _llm = llm

