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


async def dispatch(check_id: str) -> None:
    s = get_settings()
    if s.pipeline_mode == "inline":
        from app.pipeline.runner import run_check_by_id

        task = asyncio.get_running_loop().create_task(run_check_by_id(check_id))
        _background.add(task)
        task.add_done_callback(_background.discard)
        return
    topic = _topic_path()
    data = json.dumps({"check_id": check_id}).encode()
    future = _publisher.publish(topic, data)
    await asyncio.to_thread(future.result, 10)


async def drain() -> None:
    """Wait for inline pipeline tasks (tests and graceful shutdown)."""
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
