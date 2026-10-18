"""Tier 1 cache: exact keys (sha256 of bytes, normalized text, normalized URL) -> verdict ids.

Lookup runs before extraction. Near-exact media (docs/04): image pHash within Hamming distance 6,
video when 60% of keyframe pHashes are within distance 6. pHashes are indexed in
`phash_buckets/{n}{chunk}` under each of their four 16-bit chunks, so any match within 3 bits is
always found (pigeonhole) and most within 6 are, using only get/set on small docs.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.models import Label, MediaRef
from app.settings import get_config
from app.store import Store

CACHE_KEYS = "cache_keys"
VERDICTS = "verdicts"
PHASH_BUCKETS = "phash_buckets"
VIDEO_INDEX_FRAMES = 6   # keyframes indexed and looked up per video (first 30 s at 1 frame / 5 s)


def _usable(verdict: dict[str, Any], now: datetime) -> bool:
    if verdict.get("is_stub"):
        return False
    if verdict.get("status") != "ACTIVE":
        return False
    expires = verdict.get("expires_at")
    if expires and not verdict.get("pinned") and datetime.fromisoformat(expires) <= now:
        return False
    return True


async def lookup(store: Store, keys: list[str], now: datetime | None = None) -> dict[str, Any] | None:
    """Return the first matching cache entry with its usable verdict docs, or None.

    Result: {"key", "verdicts": [verdict docs], "non_checkable": {...} | None}
    """
    now = now or datetime.now(UTC)
    for key in keys:
        entry = await store.get(CACHE_KEYS, key)
        if entry and (hit := await _resolve(store, key, entry, now)):
            return hit
    return None


async def _resolve(store: Store, key: str, entry: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """A cache entry becomes a hit only if every verdict it points to is still usable."""
    if entry.get("non_checkable"):
        return {"key": key, "verdicts": [], "non_checkable": entry["non_checkable"]}
    vids = entry.get("verdict_ids") or []
    verdicts = [d for d in await asyncio.gather(*(store.get(VERDICTS, v) for v in vids)) if d and _usable(d, now)]
    if verdicts and len(verdicts) == len(vids):
        return {"key": key, "verdicts": verdicts, "non_checkable": None}
    return None


# ---------- media (exact sha256 per file, then near-exact pHash for single-file shares) ----------

def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _chunks(h: str) -> list[str]:
    return [f"{i}{h[i * 4:(i + 1) * 4]}" for i in range(4)]


def _same_target(entries: list[dict[str, Any]]) -> bool:
    first = entries[0]
    return all(e.get("verdict_ids") == first.get("verdict_ids") and e.get("non_checkable") == first.get("non_checkable")
               for e in entries)


async def lookup_media(store: Store, media: list[MediaRef], now: datetime | None = None) -> dict[str, Any] | None:
    """Tier 1 for shares with media. The caption is ignored: the same photo with a new caption hits."""
    if not media:
        return None
    now = now or datetime.now(UTC)
    keys = [f"sha256:{m.sha256}" for m in media]
    entries = await asyncio.gather(*(store.get(CACHE_KEYS, k) for k in keys))
    if all(entries) and _same_target(entries):  # type: ignore[arg-type]
        if hit := await _resolve(store, keys[0], entries[0], now):  # type: ignore[arg-type]
            return hit
    if len(media) != 1:
        return None  # near matching a set of images is ambiguous; exact only
    m = media[0]
    if m.phash:
        return await _near(store, [m.phash], "image", now)
    if m.frame_phashes:
        return await _near(store, m.frame_phashes, "video", now)
    return None


async def _near(store: Store, hashes: list[str], kind: str, now: datetime) -> dict[str, Any] | None:
    lim = get_config().limits["cache"]
    max_d = int(lim["phash_max_hamming"])
    probe = hashes[:VIDEO_INDEX_FRAMES] if kind == "video" else hashes
    bucket_ids = sorted({c for h in probe for c in _chunks(h)})
    buckets = await asyncio.gather(*(store.get(PHASH_BUCKETS, b) for b in bucket_ids))
    candidates: dict[str, dict[str, Any]] = {}
    for b in buckets:
        for eid, e in (b or {}).items():
            if isinstance(e, dict) and e.get("kind") == kind:
                candidates[eid] = e
    scored = []
    for eid, e in candidates.items():
        if kind == "image":
            d = hamming(hashes[0], e["hash"])
            if d <= max_d:
                scored.append((d, eid, e))
        else:
            frames = e.get("frames") or []
            close = sum(1 for h in hashes if frames and min(hamming(h, f) for f in frames) <= max_d)
            ratio = close / len(hashes)
            if ratio >= float(lim["video_keyframe_match_ratio"]):
                scored.append((1 - ratio, eid, e))
    for _, eid, e in sorted(scored, key=lambda x: x[0]):
        if hit := await _resolve(store, f"{kind}-phash:{eid}", e, now):
            return hit
    return None


async def write_media(
    store: Store, media: list[MediaRef], verdict_ids: list[str], non_checkable: dict[str, Any] | None = None,
) -> None:
    """Index single-file shares for near matching (exact sha256 keys go through write())."""
    if len(media) != 1:
        return
    m = media[0]
    entry: dict[str, Any] = {"verdict_ids": verdict_ids, "created_at": datetime.now(UTC).isoformat()}
    if non_checkable:
        entry["non_checkable"] = non_checkable
    eid = f"{m.kind}_{m.sha256[:16]}"
    if m.phash:
        entry |= {"kind": "image", "hash": m.phash}
        index = [m.phash]
    elif m.frame_phashes:
        entry |= {"kind": "video", "frames": m.frame_phashes}
        index = m.frame_phashes[:VIDEO_INDEX_FRAMES]
    else:
        return
    for bucket in sorted({c for h in index for c in _chunks(h)}):
        await store.set(PHASH_BUCKETS, bucket, {eid: entry}, merge=True)


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
