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

    from app.llm import _retry_once

    state = {"n": 0}

    async def flaky():
        state["n"] += 1
        if state["n"] == 1:
            raise errors.ServerError(503, {"error": {"message": "unavailable"}})
        return "ok"

    assert await _retry_once(flaky) == "ok" and state["n"] == 2


async def test_client_error_is_not_retried():
    from google.genai import errors

    from app.llm import _retry_once

    async def bad():
        raise errors.ClientError(400, {"error": {"message": "bad request"}})

    with pytest.raises(errors.ClientError):
        await _retry_once(bad)
