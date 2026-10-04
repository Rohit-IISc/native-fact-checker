from datetime import UTC, datetime

from app import quota
from app.auth import User
from app.settings import get_config


async def test_daily_limit_enforced_and_refund(store):
    user = User(uid="u1", email="u1@example.com")
    limit = get_config().limits["quota"]["checks_per_user_per_day"]
    for i in range(limit):
        ok, status = await quota.consume(store, user)
        assert ok and status.used == i + 1
    ok, status = await quota.consume(store, user)
    assert not ok and status.used == limit
    await quota.refund(store, user.uid)
    ok, _ = await quota.consume(store, user)
    assert ok


async def test_ist_day_boundary(store):
    user = User(uid="u2")
    # 18:29 UTC is 23:59 IST; 18:31 UTC is 00:01 IST next day.
    before = datetime(2026, 10, 5, 18, 29, tzinfo=UTC)
    after = datetime(2026, 10, 5, 18, 31, tzinfo=UTC)
    assert quota.day_key(before) == "20261005"
    assert quota.day_key(after) == "20261006"
    assert quota.resets_at(before).isoformat().startswith("2026-10-06T00:00:00")
    await quota.consume(store, user, before)
    assert (await quota.get_quota(store, user, after)).used == 0


async def test_judge_allowlist_gets_higher_limit(store, monkeypatch):
    cfg = get_config()
    monkeypatch.setitem(cfg.limits["quota"], "judge_allowlist", ["Judge@Example.com"])
    judge = User(uid="j1", email="judge@example.com")
    assert judge.is_judge
    assert quota.user_limit(judge) == cfg.limits["quota"]["judge_checks_per_day"]
    assert quota.user_limit(User(uid="x", email="other@example.com")) == cfg.limits["quota"]["checks_per_user_per_day"]


async def test_global_circuit_breaker(store, monkeypatch):
    monkeypatch.setitem(get_config().limits, "global_daily_new_checks", 2)
    assert await quota.consume_global(store)
    assert await quota.consume_global(store)
    assert not await quota.consume_global(store)
