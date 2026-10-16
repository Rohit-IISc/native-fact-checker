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
        self, collection: str, order_by: str, limit: int, start_after: str | None = None,
        fields: list[str] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Newest first by `order_by`. `fields` limits what is read (Firestore select)."""
        ...
    async def set_vector(self, collection: str, doc_id: str, field: str, vector: list[float]) -> None: ...
    async def find_nearest(
        self, collection: str, field: str, vector: list[float], limit: int, where_eq: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any], float]]:
        """(doc_id, doc without the vector, cosine distance), nearest first."""
        ...


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 1.0 - dot / (na * nb) if na and nb else 1.0




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
        self, collection: str, order_by: str, limit: int, start_after: str | None = None,
        fields: list[str] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        items = sorted(
            self.data.get(collection, {}).items(), key=lambda kv: kv[1].get(order_by) or "", reverse=True
        )
        if start_after:
            ids = [k for k, _ in items]
            if start_after in ids:
                items = items[ids.index(start_after) + 1 :]
        if fields:
            return [(k, {f: copy.deepcopy(v[f]) for f in fields if f in v}) for k, v in items[:limit]]
        return [(k, copy.deepcopy(v)) for k, v in items[:limit]]

    async def set_vector(self, collection: str, doc_id: str, field: str, vector: list[float]) -> None:
        await self.set(collection, doc_id, {field: list(vector)}, merge=True)

    async def find_nearest(
        self, collection: str, field: str, vector: list[float], limit: int, where_eq: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any], float]]:
        hits = []
        for doc_id, doc in self.data.get(collection, {}).items():
            if field in doc and all(doc.get(k) == v for k, v in where_eq.items()):
                hits.append((doc_id, {k: v for k, v in doc.items() if k != field},
                             _cosine_distance(vector, doc[field])))
        return copy.deepcopy(sorted(hits, key=lambda h: h[2])[:limit])


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
        self, collection: str, order_by: str, limit: int, start_after: str | None = None,
        fields: list[str] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        q = self._db.collection(collection).order_by(order_by, direction=self._fs.Query.DESCENDING)
        if start_after:
            cursor = await self._db.collection(collection).document(start_after).get()
            if cursor.exists:
                q = q.start_after(cursor)
        if fields:
            q = q.select(fields)
        return [(d.id, d.to_dict()) async for d in q.limit(limit).stream()]

    async def set_vector(self, collection: str, doc_id: str, field: str, vector: list[float]) -> None:
        from google.cloud.firestore_v1.vector import Vector

        await self._ref(collection, doc_id).set({field: Vector(vector)}, merge=True)

    async def find_nearest(
        self, collection: str, field: str, vector: list[float], limit: int, where_eq: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any], float]]:
        """Firestore vector search (needs the composite vector index in firestore.indexes.json)."""
        from google.cloud.firestore_v1.base_query import FieldFilter
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector

        q = self._db.collection(collection)
        for k, v in where_eq.items():
            q = q.where(filter=FieldFilter(k, "==", v))
        vq = q.find_nearest(vector_field=field, query_vector=Vector(vector), distance_measure=DistanceMeasure.COSINE,
                            limit=limit, distance_result_field="_distance")
        out = []
        async for d in vq.stream():
            doc = d.to_dict()
            dist = float(doc.pop("_distance", 1.0))
            doc.pop(field, None)
            out.append((d.id, doc, dist))
        return out


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = MemoryStore() if get_settings().store == "memory" else FirestoreStore()
    return _store


def set_store(store: Store | None) -> None:
    global _store
    _store = store
