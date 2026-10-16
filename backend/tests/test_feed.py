from datetime import UTC, datetime, timedelta

import pytest

from app import feed

NOW = datetime.now(UTC)


def ago(**kw) -> str:
    return (NOW - timedelta(**kw)).isoformat()


@pytest.fixture(autouse=True)
def no_memo():
    feed._memo.clear()
    yield
    feed._memo.clear()


async def verdict(store, vid, label="FALSE", created=None, **extra):
    await store.set("verdicts", vid, {
        "verdict_id": vid, "check_id": f"chk-{vid}", "label": label, "status": "ACTIVE", "is_stub": False,
        "claim_original": f"दावा {vid}", "content_language": "hi", "created_at": created or ago(minutes=1),
        "answers": {"hi": {"headline": f"शीर्षक {vid}"}, "en": {"headline": f"Headline {vid}"}},
        "evidence": [{"url": "https://pib.gov.in/x"}], **extra,
    })


async def check(store, cid, vids, created, uid="u1", status="DONE"):
    await store.set("checks", cid, {"uid": uid, "status": status, "created_at": created, "verdict_ids": vids,
                                    "request": {"text": "private post text"}})


async def test_recent_shows_only_verdict_text(store):
    await verdict(store, "v1", created=ago(minutes=3))
    await verdict(store, "v2", created=ago(minutes=2), is_stub=True)
    await verdict(store, "v3", created=ago(minutes=1), status="SUPERSEDED")
    await verdict(store, "v4", created=ago(hours=1), expires_at=ago(minutes=5))
    items = await feed.recent(store)
    assert [i["verdict_id"] for i in items] == ["v1"]
    assert items[0] == {"verdict_id": "v1", "label": "FALSE", "headline": "शीर्षक v1", "claim": "दावा v1",
                        "language": "hi", "created_at": items[0]["created_at"]}


async def test_trending_counts_checks_and_skips_internal(store):
    await verdict(store, "a")
    await verdict(store, "b", label="TRUE")
    await verdict(store, "c", label="SCAM")
    for i in range(3):
        await check(store, f"a{i}", ["a"], ago(hours=i + 1))
    await check(store, "b0", ["b"], ago(hours=2))
    await check(store, "b1", ["b", "b"], ago(hours=3))  # one check counts once
    await check(store, "c0", ["c"], ago(hours=1))
    await check(store, "seed", ["c"], ago(hours=1), uid="demo-seed")
    await check(store, "smoke", ["c"], ago(hours=1), uid="deploy-smoke")
    await check(store, "failed", ["c"], ago(hours=1), status="FAILED")
    out = await feed.trending(store)
    assert out["window"] == "24h"
    assert [(i["verdict_id"], i["checks"]) for i in out["items"]] == [("a", 3), ("b", 2), ("c", 1)]
    assert "request" not in str(out) and "private" not in str(out)


async def test_trending_widens_to_seven_days(store):
    await verdict(store, "a")
    await verdict(store, "b")
    await check(store, "a0", ["a"], ago(hours=2))
    await check(store, "b0", ["b"], ago(days=3))
    await check(store, "b1", ["b"], ago(days=4))
    await check(store, "old", ["b"], ago(days=9))
    out = await feed.trending(store)
    assert out["window"] == "7d"
    assert [(i["verdict_id"], i["checks"]) for i in out["items"]] == [("b", 2), ("a", 1)]


async def test_history_stats(store, llm):
    import httpx

    from app.main import app

    for i, label in enumerate(["FALSE", "FALSE", "SCAM", "TRUE"]):
        await store.set("users/alice/history", f"h{i}", {"label": label, "created_at": ago(minutes=i)})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/v1/me/history/stats", headers={"Authorization": "Bearer dev:alice"})
        assert r.json() == {"checked": 4, "by_label": {"FALSE": 2, "SCAM": 1, "TRUE": 1}}
        assert (await c.get("/v1/feed/recent", headers={"Authorization": "Bearer dev:alice"})).status_code == 200
        assert (await c.get("/v1/feed/trending")).status_code == 401
