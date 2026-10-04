"""Run the real pipeline in-process (no HTTP, no UI) and capture what happened.

Shared by `make try`, `make accept` and `make record`. Stage timings come from a store wrapper
that sees every set_stage() write, so the runner itself stays unaware of the CLI.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.agents import extractor
from app.devtools.recording import CapturingLLM
from app.ids import ulid
from app.intake.hashing import extract_urls, text_key, url_key
from app.intake.validate import UploadedFile, sniff, validate
from app.llm import LLM, StageFailed
from app.models import CheckRequest, CheckResult, Extraction, MediaRef
from app.observability.calls import CheckLedger, ledger_var
from app.observability.logging import check_id_var
from app.pipeline import runner
from app.pipeline.progress import CHECKS
from app.settings import get_config
from app.store import Store

DEV_UID = "dev-cli"
STAGES = ("full", "extract")


@dataclass
class StageTiming:
    stage: str
    started_s: float
    duration_ms: int | None = None


class TracingStore:
    """Wraps a Store; records each `stage` change on checks/{id} with its start time."""

    def __init__(self, inner: Store, on_stage=None) -> None:
        self.inner = inner
        self.t0 = time.monotonic()
        self.stages: list[StageTiming] = []
        self.on_stage = on_stage

    def _mark(self, stage: str) -> None:
        now = time.monotonic() - self.t0
        if self.stages and self.stages[-1].duration_ms is None:
            self.stages[-1].duration_ms = int((now - self.stages[-1].started_s) * 1000)
        if self.on_stage and self.stages:
            self.on_stage(self.stages[-1])
        self.stages.append(StageTiming(stage, now))
        if stage in ("done", "failed", "limit"):
            self.stages[-1].duration_ms = 0

    async def set(self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = False) -> None:
        if collection == CHECKS and "stage" in data:
            self._mark(data["stage"])
        await self.inner.set(collection, doc_id, data, merge=merge)

    def __getattr__(self, name: str):
        return getattr(self.inner, name)


@dataclass
class Run:
    input: dict[str, Any]
    mode: str
    started_at: str
    stages: list[StageTiming] = field(default_factory=list)
    extraction: Extraction | None = None
    result: CheckResult | None = None
    error: str | None = None
    ledger: CheckLedger = field(default_factory=CheckLedger)
    latency_ms: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.result is None:
            return "ERROR" if self.error else "-"
        if self.result.status != "DONE":
            return self.result.status
        if self.result.non_checkable_type:
            return "NOT_CHECKABLE"
        labels = [c.label.value for c in self.result.claims]
        return labels[0] if len(set(labels)) == 1 else "/".join(labels)

    @property
    def language(self) -> str | None:
        if self.result and self.result.content_language:
            return self.result.content_language
        return self.extraction.content_language if self.extraction else None

    def to_json(self) -> dict[str, Any]:
        def dump(m: BaseModel | None):
            return m.model_dump(mode="json") if m is not None else None

        return {
            "input": self.input, "mode": self.mode, "started_at": self.started_at,
            "latency_ms": self.latency_ms, "label": self.label, "language": self.language,
            "error": self.error, "notes": self.notes,
            "stages": [s.__dict__ for s in self.stages],
            "extraction": dump(self.extraction), "result": dump(self.result),
            "cost": {
                "model_usd": self.ledger.model_cost_usd, "total_usd": self.ledger.total_cost_usd,
                "grounding_queries": self.ledger.grounding_queries,
                "calls": [c.row() for c in self.ledger.calls],
            },
        }


def build_request(
    text: str | None = None, file: str | None = None, url: str | None = None
) -> tuple[CheckRequest, list[str], list[str]]:
    """Same validation and cache keys as POST /v1/checks, plus local media the API cannot take yet."""
    notes: list[str] = []
    uploads = []
    if file:
        path = Path(file).expanduser().resolve()
        data = path.read_bytes()
        if sniff(data) is None and file.endswith((".txt", ".md")):
            text = ((text or "") + "\n" + data.decode("utf-8")).strip()
        else:
            uploads.append(UploadedFile(path.name, data))
    typed = validate(text, url, uploads)
    media = [
        MediaRef(kind=kind, mime_type=mime, uri=str(Path(file).expanduser().resolve()), size_bytes=len(f.data),
                 sha256=hashlib.sha256(f.data).hexdigest())
        for f, kind, mime in typed
    ]
    if media:
        notes.append("media sent inline from a local path; the API media lane (GCS upload, pHash) is Day 2")
    url = (url or "").strip() or next(iter(extract_urls(text)), None)
    if url:
        notes.append("link fetch ladder is not built yet (Day 2): the extractor sees only the shared text")
    keys = [k for k in [text_key(text) if text else None, url_key(url) if url else None] if k]
    check_id = ulid()
    req = CheckRequest(check_id=check_id, uid=DEV_UID, text=text, url=url, media=media,
                       share_date=datetime.now(UTC).date())
    return req, keys, notes


async def run(req: CheckRequest, *, store: Store, llm: LLM, stage: str = "full",
              cache_keys: list[str] | None = None, on_stage=None) -> tuple[Run, CapturingLLM]:
    """Returns the run and the capturing LLM (its outputs are what `make record` saves)."""
    llm = CapturingLLM(llm)
    out = Run(input=req.model_dump(mode="json", include={"text", "url", "media"}), mode=stage,
              started_at=datetime.now(UTC).isoformat())
    tracing = TracingStore(store, on_stage)
    tasks_before = asyncio.all_tasks()
    check_id_var.set(req.check_id)
    t0 = time.monotonic()
    if stage == "extract":
        ledger_var.set(out.ledger)
        tracing._mark("extracting")
        try:
            out.extraction = await extractor.extract(llm, req)
        except StageFailed as e:
            out.error = str(e)
        tracing._mark("done")
    else:
        await store.set(CHECKS, req.check_id, {
            "check_id": req.check_id, "uid": req.uid, "status": "RUNNING",
            "created_at": datetime.now(UTC).isoformat(), "request": req.model_dump(mode="json"),
        })
        # run_check sets its own ledger in this context; we read it back afterwards.
        out.result = await runner.run_check(req, store=tracing, llm=llm, cache_keys=cache_keys or [])
        out.ledger = ledger_var.get() or out.ledger
        doc = await store.get(CHECKS, req.check_id) or {}
        if out.result.status == "FAILED":
            out.error = doc.get("error_code")
        raw = llm.outputs.get("extractor")
        out.extraction = extractor.finalize(raw) if isinstance(raw, Extraction) else None
    out.latency_ms = int((time.monotonic() - t0) * 1000)
    out.stages = tracing.stages
    await _drain_background_tasks(tasks_before)
    return out, llm


async def _drain_background_tasks(before: set[asyncio.Task]) -> None:
    """run_check fires write_check_run as a task; let ours finish before the loop closes.

    Only tasks started during this run: other concurrent acceptance cases are not ours to wait on.
    """
    pending = asyncio.all_tasks() - before - {asyncio.current_task()}
    if pending:
        await asyncio.wait(pending, timeout=10)


def total_budget_s(req: CheckRequest) -> float:
    return get_config().total_budget(extractor.media_seconds(req))


def save_run(run_: Run, runs_dir: Path, name: str | None = None) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = runs_dir / f"{stamp}{'-' + name if name else ''}.json"
    path.write_text(json.dumps(run_.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

