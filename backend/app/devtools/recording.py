"""Capture model outputs per stage, save them as fixtures, and replay them with no paid calls.

Fixture layout: backend/tests/fixtures/{case_id}/{stage}.json
  {"prompt_version": "...", "model_id": "...", "recorded_at": "...", "output": {...}}
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
from app.settings import get_config

T = TypeVar("T", bound=BaseModel)
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


class CapturingLLM:
    """Delegates to a real (or fake) LLM and keeps the last validated output of each stage."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner
        self.outputs: dict[str, BaseModel] = {}
        self.versions: dict[str, str] = {}

    async def generate(self, *, stage: str, prompt: str, prompt_version: str, schema: type[T],
                       media: list[MediaPart] | None = None, timeout_s: float,
                       model_key: str | None = None) -> T:
        result = await self.inner.generate(stage=stage, prompt=prompt, prompt_version=prompt_version,
                                           schema=schema, media=media, timeout_s=timeout_s, model_key=model_key)
        self.outputs[stage] = result
        self.versions[stage] = prompt_version
        return result

    def save(self, case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> list[Path]:
        case_dir = fixtures_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        cfg = get_config()
        paths = []
        for stage, output in self.outputs.items():
            path = case_dir / f"{stage}.json"
            path.write_text(json.dumps({
                "prompt_version": self.versions[stage],
                "model_id": cfg.model_for_stage(stage)["id"],
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "output": output.model_dump(mode="json"),
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            paths.append(path)
        return paths


def load_fixtures(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> dict[str, dict[str, Any]]:
    """{stage: fixture record} for one recorded case."""
    case_dir = fixtures_dir / case_id
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(case_dir.glob("*.json"))}


def replay_llm(case_id: str, fixtures_dir: Path = FIXTURES_DIR) -> FakeLLM:
    return FakeLLM({stage: rec["output"] for stage, rec in load_fixtures(case_id, fixtures_dir).items()})


def recorded_cases(fixtures_dir: Path = FIXTURES_DIR) -> list[str]:
    return sorted(p.name for p in fixtures_dir.iterdir() if p.is_dir()) if fixtures_dir.exists() else []
