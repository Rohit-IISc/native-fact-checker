"""Hand a created check to the pipeline: in-process (local) or via Pub/Sub (Cloud Run)."""
from __future__ import annotations

import asyncio
import json
import logging

from app.settings import get_settings

log = logging.getLogger(__name__)
_background: set[asyncio.Task] = set()
_publisher = None


def _topic_path() -> str:
    global _publisher
    from google.cloud import pubsub_v1

    s = get_settings()
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher.topic_path(s.gcp_project, s.pubsub_topic)


async def dispatch(check_id: str, task: str = "run") -> None:
    """task "run": the full pipeline. task "speak": audio for a check that is already DONE (a cache hit
    answered in a new language). Via Pub/Sub in Cloud Run so the work keeps CPU after the API responds."""
    s = get_settings()
    if s.pipeline_mode == "inline":
        from app.pipeline.reuse import speak_check
        from app.pipeline.runner import run_check_by_id
        from app.store import get_store

        coro = run_check_by_id(check_id) if task == "run" else speak_check(get_store(), check_id)
        job = asyncio.get_running_loop().create_task(coro)
        _background.add(job)
        job.add_done_callback(_background.discard)
        return
    topic = _topic_path()
    data = json.dumps({"check_id": check_id, "task": task}).encode()
    future = _publisher.publish(topic, data)
    await asyncio.to_thread(future.result, 10)


async def drain() -> None:
    """Wait for inline pipeline tasks (tests and graceful shutdown)."""
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
