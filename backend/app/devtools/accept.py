"""make accept [CASE=substring] [FAKE=1] | make record

Runs every case in tests/acceptance/*.yaml through the real pipeline in-process and prints a
pass/fail table with latency and cost. Each run is saved under runs/accept-{timestamp}/.
--record also writes each case's model outputs to backend/tests/fixtures/{case_id}/ for make test.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "tests" / "acceptance"

from app.devtools.try_cmd import BOLD, DIM, GREEN, RED, RESET, YELLOW  # noqa: E402


@dataclass
class Case:
    id: str
    input: dict
    language: str
    expected: list[str]
    budget_s: float | None = None
    case: str | int | None = None


@dataclass
class Outcome:
    case: Case
    status: str            # PASS | FAIL | SKIP | ERROR
    label: str = "-"
    language: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    reasons: list[str] | None = None


def load_cases(match: str | None = None) -> list[Case]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        c = Case(id=raw["id"], input=raw["input"], language=str(raw["language"]),
                 expected=[_label(x) for x in raw["expected"]], budget_s=raw.get("budget_s"), case=raw.get("case"))
        if not match or match in c.id:
            cases.append(c)
    return cases


def _label(x: object) -> str:
    # Unquoted TRUE/FALSE in YAML parse as booleans.
    return str(x).upper()


def same_language(actual: str | None, expected: str) -> bool:
    return bool(actual) and actual.split("-")[0].lower() == expected.split("-")[0].lower()


async def run_case(case: Case, runs_dir: Path, record: bool) -> Outcome:
    from app.devtools import harness
    from app.intake.validate import InvalidInput
    from app.llm import get_llm
    from app.store import MemoryStore

    inp = dict(case.input)
    file = inp.get("file")
    if file and file.startswith("gs://"):
        return Outcome(case, "SKIP", reasons=["gs:// inputs need the Day 2 media lane"])
    if file and not Path(file).is_absolute():
        file = str(ROOT / file)
    try:
        req, _keys, _notes = await harness.build_request(inp.get("text"), file, inp.get("url"))
    except (InvalidInput, OSError) as e:
        return Outcome(case, "ERROR", reasons=[f"bad input: {e}"])

    # Fresh memory store per case: acceptance measures the pipeline, not the shared cache.
    run, captured = await harness.run(req, store=MemoryStore(), llm=get_llm())
    harness.save_run(run, runs_dir, case.id)
    if record and not run.error:
        captured.save(case.id)

    budget = case.budget_s or harness.total_budget_s(req)
    reasons = []
    if run.error:
        reasons.append(f"error {run.error}")
    if run.label not in case.expected:
        reasons.append(f"label {run.label}, want {'|'.join(case.expected)}")
    if not same_language(run.language, case.language):
        reasons.append(f"language {run.language}, want {case.language}")
    if run.latency_ms > budget * 1000:
        reasons.append(f"latency {run.latency_ms / 1000:.1f}s > {budget:.0f}s")
    return Outcome(case, "FAIL" if reasons else "PASS", run.label, run.language, run.latency_ms,
                   run.ledger.total_cost_usd, reasons)


def print_table(outcomes: list[Outcome]) -> None:
    color = {"PASS": GREEN, "FAIL": RED, "ERROR": RED, "SKIP": YELLOW}
    w = max(len(o.case.id) for o in outcomes)
    print(f"\n{BOLD}{'case':<{w}}  {'result':<6}  {'label':<20}  {'lang':<6}  {'latency':>8}  {'cost':>9}  why{RESET}")
    for o in outcomes:
        lang_ok = same_language(o.language, o.case.language)
        lang = f"{o.language or '-'}" + ("" if lang_ok or o.status == "SKIP" else "!")
        print(f"{o.case.id:<{w}}  {color[o.status]}{o.status:<6}{RESET}  {o.label:<20}  {lang:<6}  "
              f"{o.latency_ms / 1000:>7.1f}s  ${o.cost_usd:>8.5f}  {DIM}{'; '.join(o.reasons or [])}{RESET}")
    n = {s: sum(o.status == s for o in outcomes) for s in ("PASS", "FAIL", "ERROR", "SKIP")}
    ran = [o for o in outcomes if o.status in ("PASS", "FAIL")]
    lang_pass = sum(same_language(o.language, o.case.language) for o in ran)
    avg = sum(o.latency_ms for o in ran) / len(ran) / 1000 if ran else 0
    print(f"\n{BOLD}{n['PASS']}/{len(outcomes)} passed{RESET}  fail={n['FAIL']} error={n['ERROR']} skip={n['SKIP']}  "
          f"language {lang_pass}/{len(ran)}  avg latency {avg:.1f}s  "
          f"total cost ${sum(o.cost_usd for o in outcomes):.4f}")


async def amain(a: argparse.Namespace) -> int:
    os.environ["STORE"] = "memory"
    os.environ.setdefault("PIPELINE_MODE", "inline")
    if a.fake:
        os.environ["LLM_MODE"] = "fake"
    from app.observability.logging import setup_logging
    from app.settings import get_settings

    setup_logging(logging.WARNING)
    cases = load_cases(a.case)
    if not cases:
        print(f"no cases match {a.case!r} in {CASES_DIR}")
        return 2
    s = get_settings()
    if a.record and s.llm_mode != "gemini":
        print("make record needs real model calls (LLM_MODE=gemini)")
        return 2
    runs_dir = ROOT / "runs" / f"accept-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"{DIM}{len(cases)} cases  llm={s.llm_mode}  jobs={a.jobs}  record={a.record}  -> "
          f"{runs_dir.relative_to(ROOT)}{RESET}")

    sem = asyncio.Semaphore(a.jobs)

    async def one(c: Case) -> Outcome:
        async with sem:
            try:
                o = await run_case(c, runs_dir, a.record)
            except Exception as e:  # noqa: BLE001  a crashed case must not hide the others
                o = Outcome(c, "ERROR", reasons=[repr(e)[:200]])
            print(f"  {o.status:<5} {c.id}  {o.latency_ms / 1000:.1f}s", flush=True)
            return o

    outcomes = await asyncio.gather(*(one(c) for c in cases))
    print_table(outcomes)
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "summary.json").write_text(json.dumps([{
        "id": o.case.id, "status": o.status, "label": o.label, "expected": o.case.expected,
        "language": o.language, "expected_language": o.case.language, "latency_ms": o.latency_ms,
        "cost_usd": o.cost_usd, "reasons": o.reasons or [],
    } for o in outcomes], ensure_ascii=False, indent=2), encoding="utf-8")
    if a.record:
        print(f"{DIM}fixtures written to backend/tests/fixtures/{RESET}")
    return 0 if all(o.status in ("PASS", "SKIP") for o in outcomes) else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="make accept", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", help="only cases whose id contains this")
    p.add_argument("--jobs", type=int, default=3, help="cases run concurrently")
    p.add_argument("--fake", action="store_true", help="LLM_MODE=fake: canned outputs, no paid calls")
    p.add_argument("--record", action="store_true", help="save model outputs to backend/tests/fixtures/")
    sys.exit(asyncio.run(amain(p.parse_args(argv))))


if __name__ == "__main__":
    main()
