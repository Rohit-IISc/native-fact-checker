"""Tier 1 cache: exact keys (sha256 of bytes, normalized text, normalized URL) -> verdict ids.

Lookup runs before extraction. pHash buckets for images and video keyframes are added with
the media lane (docs/04).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Label
from app.store import Store

CACHE_KEYS = "cache_keys"
VERDICTS = "verdicts"


def _usable(verdict: dict[str, Any], now: datetime) -> bool:
    if verdict.get("is_stub"):
        return False
    if verdict.get("status") != "ACTIVE":
        return False
    expires = verdict.get("expires_at")
    if expires and datetime.fromisoformat(expires) <= now:
        return False
    return True


async def lookup(store: Store, keys: list[str], now: datetime | None = None) -> dict[str, Any] | None:
    """Return the first matching cache entry with its usable verdict docs, or None.

    Result: {"key", "verdicts": [verdict docs], "non_checkable": {...} | None}
    """
    now = now or datetime.now(UTC)
    for key in keys:
        entry = await store.get(CACHE_KEYS, key)
        if not entry:
            continue
        if entry.get("non_checkable"):
            return {"key": key, "verdicts": [], "non_checkable": entry["non_checkable"]}
        verdicts = []
        for vid in entry.get("verdict_ids") or []:
            doc = await store.get(VERDICTS, vid)
            if doc and _usable(doc, now):
                verdicts.append(doc)
        if verdicts and len(verdicts) == len(entry.get("verdict_ids") or []):
            return {"key": key, "verdicts": verdicts, "non_checkable": None}
    return None


async def write(
    store: Store,
    keys: list[str],
    verdict_ids: list[str],
    non_checkable: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    for key in keys:
        doc: dict[str, Any] = {"type": key.split(":", 1)[0], "verdict_ids": verdict_ids, "created_at": now}
        if non_checkable:
            doc["non_checkable"] = non_checkable
        await store.set(CACHE_KEYS, key, doc)


def is_cacheable(labels: list[Label]) -> bool:
    """Failed checks are never cached; everything else is (NEE gets a short expiry on the verdict)."""
    return bool(labels)
