"""Structured model calls on Vertex AI Gemini.

Every call: model by stage key from config/models.yaml, Pydantic response schema,
deadline, one retry with the validation error appended, and a ModelCall record.
LLM_MODE=fake swaps in FakeLLM (recorded fixtures) so tests make no paid calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

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


def _thinking_config(level: str | None):
    from google.genai import types

    if not level:
        return None
    # Gemini 3 models take a thinking level; older models ignore unknown levels at our risk,
    # so fall back to no explicit config if construction fails.
    try:
        return types.ThinkingConfig(thinking_level=level.upper())
    except Exception:  # noqa: BLE001
        return None


class GeminiLLM:
    def __init__(self) -> None:
        from google import genai

        s = get_settings()
        cfg = get_config().models
        self._client = genai.Client(vertexai=True, project=s.gcp_project, location=cfg["vertex"]["location"])

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
        gen_cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
            thinking_config=_thinking_config(model.get("thinking")),
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if low_res else None,
        )
        text = prompt
        last_error = ""
        for attempt in range(2):
            started = time.monotonic()
            call = ModelCall(
                check_id=check_id_var.get(), stage=stage, model_id=model["id"],
                prompt_version=prompt_version, retry=attempt > 0,
            )
            try:
                resp = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=model["id"], contents=self._parts(text, media), config=gen_cfg
                    ),
                    timeout=timeout_s,
                )
            except TimeoutError as e:
                call.success = False
                call.latency_ms = int((time.monotonic() - started) * 1000)
                _record(call)
                raise StageFailed(stage, f"timeout after {timeout_s}s") from e
            call.latency_ms = int((time.monotonic() - started) * 1000)
            usage = resp.usage_metadata
            if usage:
                call.input_tokens = usage.prompt_token_count or 0
                call.output_tokens = usage.candidates_token_count or 0
                call.thinking_tokens = usage.thoughts_token_count or 0
            call.cost_usd = model_cost(key, call.input_tokens, call.output_tokens, call.thinking_tokens)
            try:
                result = schema.model_validate_json(resp.text or "")
                _record(call)
                return result
            except ValidationError as e:
                call.success = False
                _record(call)
                last_error = str(e)[:2000]
                text = (
                    f"{prompt}\n\nYour previous answer failed validation with this error. "
                    f"Return corrected JSON only.\n{last_error}"
                )
        raise StageFailed(stage, f"invalid output after retry: {last_error[:300]}")


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
        model_id = get_config().model_for_stage(stage)["id"] if model_key is None else model_key
        _record(ModelCall(check_id=check_id_var.get(), stage=stage, model_id=model_id,
                          prompt_version=prompt_version))
        if isinstance(value, BaseModel):
            return schema.model_validate(value.model_dump())
        return schema.model_validate(json.loads(json.dumps(value, default=str)))


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
