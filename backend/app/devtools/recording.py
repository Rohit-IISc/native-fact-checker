"""Capture model outputs per stage, save them as fixtures, and replay them with no paid calls.

Fixture layout: backend/tests/fixtures/{case_id}/{stage}.json
  {"prompt_version": "...", "model_id": "...", "recorded_at": "...", "outputs": [{...}, ...]}
plus tools.json: every tool call's result (Fact Check API, Vision, RDAP...) keyed by its arguments.
Replay is keyed by case and stage, not by prompt hash, so a prompt edit does not silently drop a
fixture; tests compare prompt_version and tell you to `make record` when it is stale.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm import LLM, FakeLLM, MediaPart
from app.models import GroundedText
from app.settings import get_config

T = TypeVar("T", bound=BaseModel)
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
TOOLS_FILE = "tools.json"


class CapturingLLM:
    """Delegates to a real (or fake) LLM and keeps the last validated output of each stage."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner
        self.outputs: dict[str, list[BaseModel]] = {}   # per stage, in call order (composer runs per claim)
        self.versions: dict[str, str] = {}

    async def generate(self, *, stage: str, prompt: str, prompt_version: str, schema: type[T],
                       media: list[MediaPart] | None = None, timeout_s: float,
                       model_key: str | None = None) -> T:
        slot = self._reserve(stage, prompt_version)
        result = await self.inner.generate(stage=stage, prompt=prompt, prompt_version=prompt_version,
                                           schema=schema, media=media, timeout_s=timeout_s, model_key=model_key)
        self.outputs[stage][slot] = result
        return result

    async def search(self, *, stage: str, prompt: str, prompt_version: str, timeout_s: float) -> GroundedText:
        slot = self._reserve(stage, prompt_version)
        result = await self.inner.search(stage=stage, prompt=prompt, prompt_version=prompt_version,
                                         timeout_s=timeout_s)
        self.outputs[stage][slot] = result
        return result

    def _reserve(self, stage: str, prompt_version: str) -> int:
        """Record outputs in call-start order, which is the order replay hands them out. Parallel calls
        (native and English composer) finish in any order; recording on completion swapped them."""
        self.versions[stage] = prompt_version
        self.outputs.setdefault(stage, []).append(None)  # type: ignore[arg-type]
        return len(self.outputs[stage]) - 1

    def save(self, case_id: str, tool_calls: dict[str, Any] | None = None,
             fixtures_dir: Path = FIXTURES_DIR) -> list[Path]:
        """Replace the case's fixtures with this run: one file per model stage, plus tools.json."""
        case_dir = fixtures_dir / case_id
        if case_dir.exists():
            for old in case_dir.glob("*.json"):
                old.unlink()
        case_dir.mkdir(parents=True, exist_ok=True)
        cfg = get_config()
        paths = []
        for stage, outputs in self.outputs.items():
            path = case_dir / f"{stage}.json"
            path.write_text(json.dumps({
                "prompt_version": self.versions[stage],
                "model_id": cfg.model_for_stage(stage)["id"],
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "outputs": [o.model_dump(mode="json") for o in outputs if o is not None],
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            paths.append(path)
        if tool_calls is not None:
            path = case_dir / TOOLS_FILE
            path.write_text(json.dumps(tool_calls, ensure_ascii=False, indent=1, default=str) + "\n",
                            encoding="utf-8")
            paths.append(path)
        return paths


def load_fixtures(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> dict[str, dict[str, Any]]:
    """{stage: fixture record} for one recorded case (model stages only)."""
    case_dir = fixtures_dir / case_id
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(case_dir.glob("*.json"))
            if p.name != TOOLS_FILE}


def load_tool_calls(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> dict[str, Any]:
    path = fixtures_dir / case_id / TOOLS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _sequence(outputs: list[dict]):
    """Replay a stage's outputs in call order; the last one repeats if called more often."""
    calls = iter(range(10_000))

    def next_output(_prompt: str) -> dict:
        return outputs[min(next(calls), len(outputs) - 1)]

    return next_output


def replay_llm(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> FakeLLM:
    fixtures = {}
    for stage, rec in load_fixtures(case_id, fixtures_dir).items():
        outputs = rec.get("outputs") or [rec["output"]]
        fixtures[stage] = _sequence(outputs)
    return FakeLLM(fixtures)


def recorded_cases(fixtures_dir: Path = FIXTURES_DIR) -> list[str]:
    return sorted(p.name for p in fixtures_dir.iterdir() if p.is_dir()) if fixtures_dir.exists() else []
