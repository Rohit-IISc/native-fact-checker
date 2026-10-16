import httpx
import pytest

from app.llm import StageFailed
from app.main import app
from app.pipeline.dispatch import drain
from app.settings import get_config

AUTH = {"Authorization": "Bearer dev:alice"}


@pytest.fixture
async def client(store, llm):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def post(client, headers=AUTH, **form):
    return await client.post("/v1/checks", data=form, headers=headers)


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"]


async def test_auth_required(client):
    r = await post(client, headers={}, text="x")
    assert r.status_code == 401
    r = await post(client, headers={"Authorization": "Bearer not-a-dev-token"}, text="x")
    assert r.status_code == 401


async def test_empty_share_rejected(client):
    r = await post(client, text="   ")
    assert r.status_code == 400 and r.json()["error_code"] == "EMPTY"


async def test_text_lane_end_to_end_hindi(client, store, llm):
    r = await post(client, text="फॉरवर्ड किया गया\nसरकार सभी को 5000 रुपये दे रही है। अभी लिंक पर क्लिक करें", client_lang="hi")
    assert r.status_code == 202, r.text
    check_id = r.json()["check_id"]
    await drain()

    r = await client.get(f"/v1/checks/{check_id}", headers=AUTH)
    doc = r.json()
    assert doc["status"] == "DONE" and doc["stage"] == "done" and doc["progress"] == 100
    assert "request" not in doc and "uid" not in doc
    result = doc["result"]
    assert result["content_language"] == "hi-IN"
    claim = result["claims"][0]
    assert claim["label"] == "NOT_ENOUGH_EVIDENCE"
    assert claim["answer"]["language"] == "hi-IN" and claim["answer_en"]["language"] == "en"
    assert "सरकार सभी को 5000 रुपये" in claim["claim_original"]
    assert claim["result_url"] == f"https://factcheck.test/r/{claim['verdict_id']}"

    # The extractor prompt carried the shared rules and the user text inside the data block.
    prompt = llm.prompts["extractor"][0]
    assert prompt.startswith("Shared rules") and "<user_content>" in prompt

    # History, quota and public result page.
    hist = (await client.get("/v1/me/history", headers=AUTH)).json()["items"]
    assert hist[0]["check_id"] == check_id and hist[0]["label"] == "NOT_ENOUGH_EVIDENCE"
    assert (await client.get("/v1/me/quota", headers=AUTH)).json()["used"] == 1
    pub = (await client.get(f"/v1/results/{claim['verdict_id']}?lang=hi-IN")).json()
    assert pub["label"] == "NOT_ENOUGH_EVIDENCE" and "uid" not in pub and "check_id" not in pub

    # Owner only.
    r = await client.get(f"/v1/checks/{check_id}", headers={"Authorization": "Bearer dev:mallory"})
    assert r.status_code == 404


async def test_greeting_is_not_checkable_and_repeat_hits_tier1(client):
    r = await post(client, text="🌸 Good morning! Have a blessed day 🙏")
    await drain()
    doc = (await client.get(f"/v1/checks/{r.json()['check_id']}", headers=AUTH)).json()
    assert doc["result"]["non_checkable_type"] == "GREETING"
    assert doc["result"]["claims"] == []

    r = await post(client, text="Forwarded\nGOOD MORNING!   have a blessed day")
    assert r.status_code == 200
    body = r.json()
    assert body["cache_tier_hit"] == "T1" and body["result"]["non_checkable_type"] == "GREETING"


async def test_tier1_hit_on_real_verdict_for_any_user(client, store):
    r = await post(client, text="The moon is made of cheese.")
    await drain()
    doc = (await client.get(f"/v1/checks/{r.json()['check_id']}", headers=AUTH)).json()
    vid = doc["result"]["claims"][0]["verdict_id"]
    # Simulate a real (non-stub) verdict; stubs are never served from cache.
    v = await store.get("verdicts", vid)
    await store.set("verdicts", vid, {**v, "is_stub": False})

    r = await post(client, headers={"Authorization": "Bearer dev:bob"}, text="the moon is made of cheese. 🧀")
    assert r.status_code == 200 and r.json()["cache_tier_hit"] == "T1"
    assert r.json()["result"]["claims"][0]["verdict_id"] == vid


async def test_daily_limit(client):
    limit = get_config().limits["quota"]["checks_per_user_per_day"]
    for i in range(limit):
        r = await post(client, text=f"Claim number {i} about something.")
        assert r.status_code == 202
    await drain()
    r = await post(client, text="One more claim.")
    assert r.status_code == 429
    assert r.json()["error_code"] == "DAILY_LIMIT" and "resets_at" in r.json()


async def test_extraction_failure_marks_failed_and_refunds(client, llm):
    def boom(prompt):
        raise StageFailed("extractor", "timeout")

    llm.fixtures["extractor"] = boom
    r = await post(client, text="Some claim")
    await drain()
    doc = (await client.get(f"/v1/checks/{r.json()['check_id']}", headers=AUTH)).json()
    assert doc["status"] == "FAILED" and doc["error_code"] == "EXTRACTION_FAILED"
    assert (await client.get("/v1/me/quota", headers=AUTH)).json()["used"] == 0


async def test_unknown_file_type_rejected(client):
    r = await client.post("/v1/checks", headers=AUTH, files={"files": ("a.bin", b"not a media file" * 10, None)})
    assert r.status_code == 400 and r.json()["error_code"] == "UNSUPPORTED_TYPE"


async def test_consent_and_me(client):
    assert (await client.get("/v1/me", headers=AUTH)).json()["consent_at"] is None
    assert (await client.post("/v1/me/consent", json={"ui_language": "ta"}, headers=AUTH)).status_code == 204
    me = (await client.get("/v1/me", headers=AUTH)).json()
    assert me["consent_at"] and me["ui_language"] == "ta"
    assert (await client.put("/v1/me/language", json={"ui_language": "kn"}, headers=AUTH)).status_code == 204
    assert (await client.get("/v1/me", headers=AUTH)).json()["ui_language"] == "kn"
    assert (await client.put("/v1/me/language", json={"ui_language": "xx"}, headers=AUTH)).status_code == 422
    from app.store import get_store

    await get_store().set("checks", "c-alice", {"uid": "alice", "request": {"text": "my post"}})
    await get_store().set("checks", "c-bob", {"uid": "bob"})
    assert (await client.delete("/v1/me", headers=AUTH)).status_code == 204
    assert await get_store().get("checks", "c-alice") is None
    assert await get_store().get("checks", "c-bob") is not None
    assert (await client.get("/v1/me", headers=AUTH)).json()["consent_at"] is None


async def test_pipeline_endpoint_is_idempotent(client, store):
    import base64
    import json

    r = await post(client, text="A claim to check.")
    check_id = r.json()["check_id"]
    await drain()
    before = await store.get("checks", check_id)
    msg = {"message": {"data": base64.b64encode(json.dumps({"check_id": check_id}).encode()).decode()}}
    r = await client.post("/internal/pipeline", json=msg)
    assert r.status_code == 204
    after = await store.get("checks", check_id)
    assert after["verdict_ids"] == before["verdict_ids"]
    r = await client.post("/internal/pipeline", json={"message": {"data": "!!"}})
    assert r.status_code == 204


async def test_api_prefix_from_hosting_rewrite(client):
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    r = await client.get("/api/v1/me/quota", headers=AUTH)
    assert r.status_code == 200 and r.json()["used"] == 0


async def test_model_api_error_fails_the_stage_not_the_check(client, store, llm):
    """A Vertex 5xx in the extractor is a graceful EXTRACTION_FAILED, never an INTERNAL crash."""
    llm.fixtures["extractor"] = lambda _p: StageFailed("extractor", "model API error: ServerError: 503")
    r = await post(client, text="सरकार सभी को मुफ्त लैपटॉप दे रही है")
    await drain()
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["status"] == "FAILED" and doc["error_code"] == "EXTRACTION_FAILED"
    assert "error_detail" not in (await client.get(f"/v1/checks/{doc['check_id']}", headers=AUTH)).json()


async def test_extraction_timeout_is_retried_once_when_time_allows(client, store, llm):
    calls = {"n": 0}
    base = llm.fixtures["extractor"]

    def flaky(prompt):
        calls["n"] += 1
        return StageFailed("extractor", "timeout after 25.0s") if calls["n"] == 1 else base(prompt)

    llm.fixtures["extractor"] = flaky
    r = await post(client, text="सरकार सभी को मुफ्त लैपटॉप दे रही है")
    await drain()
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["status"] == "DONE" and calls["n"] == 2
