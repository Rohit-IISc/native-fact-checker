"""Answer audio with Gemini TTS (docs/03 stage 8).

Voice per language from config/languages.yaml, style from prompts/11_tts_style.md (a block: no JSON
shared rules). Gemini returns 24 kHz 16-bit mono PCM; ffmpeg turns it into MP3 for phones.
Run as a script to hear one line:  uv run python -m app.output.tts --say "नमस्ते" --lang hi-IN
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

from app.llm import StageFailed, _hedged, _record, _retry_transient
from app.observability.calls import ModelCall
from app.observability.logging import check_id_var
from app.prompts import load_block
from app.settings import get_config, get_settings

log = logging.getLogger(__name__)
STYLE = "11_tts_style.md"
LANGUAGE_NAMES = {"hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "id": "Indonesian", "en": "English"}
PCM_RATE = 24000
_client = None


def voice_for(language: str) -> str:
    langs = get_config().languages.get("demo_languages") or {}
    return (langs.get(language.split("-")[0].lower()) or {}).get("tts_voice") or "Kore"


def tts_input(script: str, language: str) -> str:
    """Style instructions, then the words to speak. Gemini TTS follows the instructions without reading them."""
    name = LANGUAGE_NAMES.get(language.split("-")[0].lower(), language)
    style = load_block(STYLE).render(answer_language_name=name).split("\n\n", 1)[-1].strip()
    return f"{style}\n\n{script.strip()}"


async def _pcm_to_mp3(pcm: bytes) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", "pipe:0",
        "-codec:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate(pcm)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg: {err.decode()[:200]}")
    return out


async def synthesize(script: str, language: str, *, timeout_s: float | None = None) -> bytes:
    """MP3 bytes of `script` spoken in `language`. Raises StageFailed("tts", ...) on any failure."""
    global _client
    from google import genai
    from google.genai import types

    m = get_config().models["models"]["tts"]
    timeout_s = timeout_s or get_config().timeout("tts")
    if _client is None:
        _client = genai.Client(vertexai=True, project=get_settings().gcp_project, location=m.get("location", "global"))
    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_for(language)))),
    )
    call = ModelCall(check_id=check_id_var.get(), stage="tts", model_id=m["id"],
                     prompt_version=load_block(STYLE).version)
    started = time.monotonic()
    try:
        contents = tts_input(script, language)
        resp = await _retry_transient(lambda: _hedged(
            lambda: _client.aio.models.generate_content(model=m["id"], contents=contents, config=cfg),
            timeout_s, m.get("hedge_after_s"), "tts"))
        pcm = b"".join(p.inline_data.data for p in resp.candidates[0].content.parts if p.inline_data)
        if not pcm:
            raise RuntimeError("no audio in response")
        mp3 = await _pcm_to_mp3(pcm)
    except Exception as e:  # noqa: BLE001  audio is optional; the text answer stands on its own
        call.success = False
        call.latency_ms = int((time.monotonic() - started) * 1000)
        _record(call)
        raise StageFailed("tts", f"{type(e).__name__}: {str(e)[:200]}") from e
    call.latency_ms = int((time.monotonic() - started) * 1000)
    call.cost_usd = float(m.get("est_cost_per_answer", 0))
    _record(call)
    return mp3


def audio_object(verdict_id: str, language: str) -> str:
    return f"audio/{verdict_id}_{language}.mp3"


async def store_audio(verdict_id: str, language: str, mp3: bytes) -> str:
    """Save to the outputs bucket (or a local dir with STORE=memory). Returns where it was put."""
    s = get_settings()
    name = audio_object(verdict_id, language)
    if s.store == "memory" or not s.outputs_bucket:
        path = Path("/tmp/factcheck-outputs") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, mp3)
        return str(path)
    from app.intake.media import _upload_gcs

    await asyncio.to_thread(_upload_gcs, s.outputs_bucket, name, mp3, "audio/mpeg")
    return f"gs://{s.outputs_bucket}/{name}"


async def read_audio(verdict_id: str, language: str) -> bytes | None:
    s = get_settings()
    name = audio_object(verdict_id, language)
    try:
        if s.store == "memory" or not s.outputs_bucket:
            return await asyncio.to_thread((Path("/tmp/factcheck-outputs") / name).read_bytes)
        from app.intake.media import _download_gcs

        return await asyncio.to_thread(_download_gcs, s.outputs_bucket, name)
    except Exception:  # noqa: BLE001  missing or not ready yet
        return None


def audio_url(verdict_id: str, language: str) -> str:
    """Public URL of an answer's audio, served by GET /v1/results/{id}/audio (the bucket stays private)."""
    return f"{get_settings().public_base_url}/api/v1/results/{verdict_id}/audio?lang={language}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", required=True)
    ap.add_argument("--lang", default="hi-IN")
    ap.add_argument("--out", default="tts-sample.mp3")
    a = ap.parse_args()
    data = asyncio.run(synthesize(a.say, a.lang, timeout_s=60))
    Path(a.out).write_bytes(data)
    print(f"wrote {a.out} ({len(data)} bytes, voice {voice_for(a.lang)})")
