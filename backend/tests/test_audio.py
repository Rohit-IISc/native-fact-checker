"""Spoken answers: generated after DONE, attached to the verdict and the check, served by the API."""
import httpx

from app.main import app
from app.output import tts
from app.pipeline import reuse
from app.pipeline.dispatch import drain
from app.pipeline.results import VERDICTS

AUTH = {"Authorization": "Bearer dev:alice"}
MP3 = b"ID3\x03\x00\x00\x00fake-mp3-bytes"


async def test_audio_is_generated_after_done_and_served(store, llm, monkeypatch, tmp_path):
    spoken = []

    async def fake_synth(script, language, *, timeout_s=None):
        spoken.append((language, script))
        return MP3

    monkeypatch.setattr(reuse, "tts_enabled", lambda: True)
    monkeypatch.setattr(tts, "synthesize", fake_synth)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/checks", headers=AUTH, data={"text": "सरकार सभी को मुफ्त लैपटॉप दे रही है"})
        await drain()
        doc = await store.get("checks", r.json()["check_id"])
        claim = doc["result"]["claims"][0]
        assert doc["status"] == "DONE" and doc["result"]["audio_pending"] is False
        assert spoken and spoken[0][0] == "hi-IN"  # the content language, not the UI language
        assert claim["audio_url"].endswith(f"/api/v1/results/{claim['verdict_id']}/audio?lang=hi-IN")
        verdict = await store.get(VERDICTS, claim["verdict_id"])
        assert any(a.get("audio_url") for a in verdict["answers"].values())
        audio = await c.get(f"/v1/results/{claim['verdict_id']}/audio", params={"lang": "hi-IN"})
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg" and audio.content == MP3


async def test_tts_failure_keeps_the_text_answer(store, llm, monkeypatch):
    from app.llm import StageFailed

    async def broken(*a, **k):
        raise StageFailed("tts", "quota")

    monkeypatch.setattr(reuse, "tts_enabled", lambda: True)
    monkeypatch.setattr(tts, "synthesize", broken)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/checks", headers=AUTH, data={"text": "सरकार सभी को मुफ्त लैपटॉप दे रही है"})
        await drain()
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["status"] == "DONE" and doc["result"]["claims"][0]["audio_url"] is None
    assert doc["result"]["audio_pending"] is False


async def test_missing_audio_is_404():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/v1/results/nope/audio", params={"lang": "hi-IN"})
    assert r.status_code == 404
