"""llm._hedged: a stalled model call is duplicated and the faster answer wins."""
import asyncio

import pytest

from app.llm import _hedged


def calls(*delays):
    """make_call() returns coroutines that sleep the given delays in order, then return the index."""
    state = {"n": 0}

    def make_call():
        i = state["n"]
        state["n"] += 1

        async def go():
            await asyncio.sleep(delays[i])
            return i

        return go()

    return make_call, state


async def test_fast_call_is_not_hedged():
    make, state = calls(0.01, 0.01)
    assert await _hedged(make, 1.0, 0.2, "t") == 0 and state["n"] == 1


async def test_stalled_call_is_hedged_and_duplicate_wins():
    make, state = calls(5.0, 0.01)
    assert await _hedged(make, 2.0, 0.05, "t") == 1 and state["n"] == 2


async def test_both_slow_times_out():
    make, _ = calls(5.0, 5.0)
    with pytest.raises(TimeoutError):
        await _hedged(make, 0.2, 0.05, "t")


async def test_error_in_one_call_falls_back_to_the_other():
    state = {"n": 0}

    def make():
        i = state["n"]
        state["n"] += 1

        async def go():
            if i == 0:
                await asyncio.sleep(0.1)
                raise RuntimeError("boom")
            await asyncio.sleep(0.2)
            return "ok"

        return go()

    assert await _hedged(make, 2.0, 0.05, "t") == "ok"


async def test_transient_server_error_is_retried_once():
    from google.genai import errors

    from app.llm import _retry_transient

    state = {"n": 0}

    async def flaky():
        state["n"] += 1
        if state["n"] == 1:
            raise errors.ServerError(503, {"error": {"message": "unavailable"}})
        return "ok"

    assert await _retry_transient(flaky) == "ok" and state["n"] == 2


async def test_client_error_is_not_retried():
    from google.genai import errors

    from app.llm import _retry_transient

    async def bad():
        raise errors.ClientError(400, {"error": {"message": "bad request"}})

    with pytest.raises(errors.ClientError):
        await _retry_transient(bad)


async def test_rate_limit_is_retried_with_backoff(monkeypatch):
    from google.genai import errors

    from app import llm

    monkeypatch.setattr(llm, "RETRY_DELAYS_S", (0.01, 0.01, 0.01))
    state = {"n": 0}

    async def busy():
        state["n"] += 1
        if state["n"] < 3:
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        return "ok"

    assert await llm._retry_transient(busy) == "ok" and state["n"] == 3


async def test_retries_stop_when_the_budget_is_spent(monkeypatch):
    from google.genai import errors

    from app import llm

    monkeypatch.setattr(llm, "RETRY_DELAYS_S", (1.0, 1.0, 1.0))

    async def busy():
        raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})

    with pytest.raises(errors.ClientError):
        await llm._retry_transient(busy, budget_s=0.5)  # no time for even one 1 s wait


async def test_429s_are_counted_on_the_call_even_when_a_retry_recovers(monkeypatch):
    from google.genai import errors

    from app import llm
    from app.observability.calls import ModelCall

    monkeypatch.setattr(llm, "RETRY_DELAYS_S", (0.01, 0.01, 0.01))
    call = ModelCall(check_id="c", stage="judge", model_id="m", prompt_version="v")
    state = {"n": 0}

    async def busy():
        state["n"] += 1
        if state["n"] == 1:
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        if state["n"] == 2:
            raise errors.ServerError(503, {"error": {"message": "unavailable"}})
        return "ok"

    assert await llm._retry_transient(busy, call=call) == "ok"
    assert (call.rate_limited, call.server_errors, call.error_code) == (1, 1, None)
    assert call.created_at  # every row has a time, for the 429-by-hour view


def test_error_codes():
    from google.genai import errors
    from pydantic import BaseModel, ValidationError

    from app.llm import error_code

    class M(BaseModel):
        x: int

    try:
        M.model_validate({"x": "no"})
    except ValidationError as e:
        assert error_code(e) == "VALIDATION"
    assert error_code(TimeoutError()) == "TIMEOUT"
    assert error_code(errors.ClientError(429, {"error": {"message": "busy"}})) == "429"


def _call():
    from app.observability.calls import ModelCall

    return ModelCall(check_id="c", stage="judge", model_id="gemini-2.5-pro", prompt_version="v")


PRO = {"id": "gemini-2.5-pro", "thinking_budget": 1024, "hedge_after_s": 14,
       "fallback": {"id": "gemini-3.1-pro-preview", "thinking": "low"}}


async def test_final_429_moves_to_the_fallback_with_its_own_thinking_settings():
    from google.genai import errors

    from app.llm import _with_fallback

    seen = []

    async def run(m, t):
        seen.append((m["id"], m.get("thinking"), m.get("thinking_budget"), m.get("hedge_after_s")))
        if m["id"] == "gemini-2.5-pro":
            raise errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
        return "ok"

    call = _call()
    assert await _with_fallback(run, PRO, 30, call) == "ok"
    assert seen[1] == ("gemini-3.1-pro-preview", "low", None, 14)
    assert call.fallback and call.model_id == "gemini-3.1-pro-preview"


async def test_no_fallback_on_timeout_bad_request_or_too_little_time():
    from google.genai import errors

    from app.llm import _with_fallback

    for exc, budget in [(TimeoutError(), 30), (errors.ClientError(400, {"error": {"message": "bad"}}), 30),
                        (errors.ServerError(503, {"error": {"message": "x"}}), 3)]:
        async def run(m, t, exc=exc):
            raise exc

        with pytest.raises(type(exc)):
            await _with_fallback(run, PRO, budget, _call())
