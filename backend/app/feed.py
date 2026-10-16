"""Home "Recent checks" and the Trending screen: shared verdicts seen by all users.

Privacy rule (UI brief, Oct 16): an item carries only the verdict's label, the claim and its headline in the
content's language, the language and a time. Never the post, its media, a check id or anything about who
checked it. NOT_CHECKABLE results never become verdicts, so they never show. Results are kept in memory for
`feed.cache_seconds` so a busy Home screen does not re-read Firestore on every load.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.cache.tier1 import _usable
from app.pipeline.progress import CHECKS
from app.pipeline.results import VERDICTS, pick_answer
from app.settings import get_config
from app.store import Store

_VERDICT_FIELDS = ["label", "claim_original", "content_language", "answers", "created_at", "status",
                   "expires_at", "is_stub"]
_memo: dict[str, tuple[float, Any]] = {}


def _cfg() -> dict[str, Any]:
    return get_config().limits["feed"]


def item(verdict_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    answer = pick_answer(doc, doc.get("content_language")) or {}
    return {
        "verdict_id": verdict_id,  # opens the public result page, which already holds no personal data
        "label": doc.get("label"),
        "headline": answer.get("headline") or "",
        "claim": doc.get("claim_original") or "",
        "language": doc.get("content_language"),
        "created_at": doc.get("created_at"),
    }


def _shown(doc: dict[str, Any] | None, now: datetime) -> bool:
    return bool(doc) and _usable(doc, now) and doc.get("label") != "NOT_CHECKABLE"


async def _memoised(key: str, make):
    hit = _memo.get(key)
    if hit and time.monotonic() - hit[0] < float(_cfg()["cache_seconds"]):
        return hit[1]
    value = await make()
    _memo[key] = (time.monotonic(), value)
    return value


async def recent(store: Store) -> list[dict[str, Any]]:
    async def make():
        n = int(_cfg()["recent_items"])
        now = datetime.now(UTC)
        docs = await store.list_recent(VERDICTS, "created_at", n * 4, fields=_VERDICT_FIELDS)
        return [item(vid, d) for vid, d in docs if _shown(d, now)][:n]
    return await _memoised("recent", make)


async def trending(store: Store) -> dict[str, Any]:
    """Verdicts ranked by how many checks reached them (fresh runs and cache hits alike)."""
    async def make():
        cfg = _cfg()
        now = datetime.now(UTC)
        internal = set(cfg["internal_uids"])
        wide_cutoff = (now - timedelta(days=int(cfg["trending_wide_days"]))).isoformat()
        short_cutoff = (now - timedelta(hours=int(cfg["trending_hours"]))).isoformat()
        rows = await store.list_recent(CHECKS, "created_at", int(cfg["scan_checks"]),
                                       fields=["uid", "status", "created_at", "verdict_ids"])
        short, wide = Counter(), Counter()
        last: dict[str, str] = {}
        for _, c in rows:
            created = c.get("created_at") or ""
            if created < wide_cutoff:
                break
            if c.get("status") != "DONE" or c.get("uid") in internal:
                continue
            for vid in dict.fromkeys(c.get("verdict_ids") or []):
                wide[vid] += 1
                last.setdefault(vid, created)
                if created >= short_cutoff:
                    short[vid] += 1

        async def ranked(counts: Counter) -> list[dict[str, Any]]:
            out = []
            for vid, n in counts.most_common():
                doc = await store.get(VERDICTS, vid)
                if _shown(doc, now):
                    out.append(item(vid, doc) | {"checks": n, "last_checked_at": last[vid]})
                if len(out) == int(cfg["trending_items"]):
                    break
            return out

        items = await ranked(short)
        window = f"{int(cfg['trending_hours'])}h"
        if len(items) < int(cfg["trending_min_items"]):
            items, window = await ranked(wide), f"{int(cfg['trending_wide_days'])}d"
        return {"window": window, "items": items}
    return await _memoised("trending", make)
