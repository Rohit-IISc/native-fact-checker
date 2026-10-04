"""Document store. Firestore in dev and prod; an in-memory store for tests and offline UI work.

All writes go through the backend (Admin SDK); clients only read their own checks
and history via Firestore security rules.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any, Protocol

from app.settings import get_settings


class Store(Protocol):
    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...
    async def set(self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = False) -> None: ...
    async def delete(self, collection: str, doc_id: str) -> None: ...
    async def increment_if_below(self, collection: str, doc_id: str, limit: int) -> tuple[bool, int]:
        """Atomically add 1 to `count` unless it is already >= limit. Returns (allowed, new_count)."""
        ...
    async def decrement(self, collection: str, doc_id: str) -> None: ...
    async def list_recent(
        self, collection: str, order_by: str, limit: int, start_after: str | None = None
    ) -> list[tuple[str, dict[str, Any]]]: ...


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self.data.get(collection, {}).get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    async def set(self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = False) -> None:
        col = self.data.setdefault(collection, {})
        if merge and doc_id in col:
            col[doc_id].update(copy.deepcopy(data))
        else:
            col[doc_id] = copy.deepcopy(data)

    async def delete(self, collection: str, doc_id: str) -> None:
        self.data.get(collection, {}).pop(doc_id, None)

    async def increment_if_below(self, collection: str, doc_id: str, limit: int) -> tuple[bool, int]:
        async with self._lock:
            col = self.data.setdefault(collection, {})
            count = int(col.get(doc_id, {}).get("count", 0))
            if count >= limit:
                return False, count
            col[doc_id] = {**col.get(doc_id, {}), "count": count + 1}
            return True, count + 1

    async def decrement(self, collection: str, doc_id: str) -> None:
        async with self._lock:
            doc = self.data.setdefault(collection, {}).get(doc_id)
            if doc and doc.get("count", 0) > 0:
                doc["count"] -= 1

    async def list_recent(
        self, collection: str, order_by: str, limit: int, start_after: str | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        items = sorted(
            self.data.get(collection, {}).items(), key=lambda kv: kv[1].get(order_by) or "", reverse=True
        )
        if start_after:
            ids = [k for k, _ in items]
            if start_after in ids:
                items = items[ids.index(start_after) + 1 :]
        return [(k, copy.deepcopy(v)) for k, v in items[:limit]]


class FirestoreStore:
    def __init__(self) -> None:
        from google.cloud import firestore

        s = get_settings()
        self._fs = firestore
        self._db = firestore.AsyncClient(project=s.gcp_project or None, database=s.firestore_db)

    def _ref(self, collection: str, doc_id: str):
        return self._db.collection(collection).document(doc_id)

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snap = await self._ref(collection, doc_id).get()
        return snap.to_dict() if snap.exists else None

    async def set(self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = False) -> None:
        await self._ref(collection, doc_id).set(data, merge=merge)

    async def delete(self, collection: str, doc_id: str) -> None:
        await self._ref(collection, doc_id).delete()

    async def increment_if_below(self, collection: str, doc_id: str, limit: int) -> tuple[bool, int]:
        ref = self._ref(collection, doc_id)
        fs = self._fs

        @fs.async_transactional
        async def txn(transaction) -> tuple[bool, int]:
            snap = await ref.get(transaction=transaction)
            count = int((snap.to_dict() or {}).get("count", 0)) if snap.exists else 0
            if count >= limit:
                return False, count
            transaction.set(ref, {"count": count + 1, "updated_at": fs.SERVER_TIMESTAMP}, merge=True)
            return True, count + 1

        return await txn(self._db.transaction())

    async def decrement(self, collection: str, doc_id: str) -> None:
        await self._ref(collection, doc_id).set({"count": self._fs.Increment(-1)}, merge=True)

    async def list_recent(
        self, collection: str, order_by: str, limit: int, start_after: str | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        q = self._db.collection(collection).order_by(order_by, direction=self._fs.Query.DESCENDING)
        if start_after:
            cursor = await self._db.collection(collection).document(start_after).get()
            if cursor.exists:
                q = q.start_after(cursor)
        return [(d.id, d.to_dict()) async for d in q.limit(limit).stream()]


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = MemoryStore() if get_settings().store == "memory" else FirestoreStore()
    return _store


def set_store(store: Store | None) -> None:
    global _store
    _store = store
