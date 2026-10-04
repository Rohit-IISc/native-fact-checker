"""Progress updates on checks/{check_id}. Every stage writes here so the live screen moves."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Stage
from app.observability.logging import stage_var
from app.store import Store

CHECKS = "checks"

PROGRESS = {
    Stage.RECEIVED: 5,
    Stage.CACHE_LOOKUP: 10,
    Stage.FETCHING_LINK: 15,
    Stage.EXTRACTING: 25,
    Stage.SEARCHING: 45,
    Stage.PACKAGING: 60,
    Stage.JUDGING: 70,
    Stage.REVIEWING: 80,
    Stage.COMPOSING: 88,
    Stage.SPEAKING: 95,
    Stage.DONE: 100,
    Stage.FAILED: 100,
    Stage.LIMIT: 100,
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def set_stage(store: Store, check_id: str, stage: Stage, **extra: Any) -> None:
    stage_var.set(stage.value)
    await store.set(
        CHECKS,
        check_id,
        {
            "stage": stage.value,
            "stage_label_key": f"stage.{stage.value}",
            "progress": PROGRESS[stage],
            "updated_at": now_iso(),
            **extra,
        },
        merge=True,
    )


async def set_agent_status(store: Store, check_id: str, agent: str, status: str) -> None:
    """Sub-agent ticks on the live screen: pending, done, timeout, skipped, failed."""
    check = await store.get(CHECKS, check_id) or {}
    agents = dict(check.get("agents") or {})
    agents[agent] = status
    await store.set(CHECKS, check_id, {"agents": agents, "updated_at": now_iso()}, merge=True)
