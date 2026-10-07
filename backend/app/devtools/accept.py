"""make accept [CASE=substring] [FAKE=1] | make record

Runs every case in tests/acceptance/*.yaml through the real pipeline in-process and prints a
pass/fail table with latency and cost. Each run is saved under runs/accept-{timestamp}/.
--record also writes each case's model outputs to backend/tests/fixtures/{case_id}/ for make test,
except for cases built from samples/ (third-party posts stay local; the repo is public).

Case fields beyond input/language/expected (see tests/acceptance/README.md):
  gold: [urls]              published fact checks for this case; the table reports whether the
                            pipeline cited the same page ("page"), the same publisher ("site") or neither
  after: <case id>          run right after that case in the same store, with the API's tier 1 lookup
  expect_cache: T1|T2       the case must be answered from that cache tier
  expect_ai_generation: true  the verdict must carry an AI-generation assessment
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

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
    gold: list[str] = field(default_factory=list)
    after: str | None = None
    expect_cache: str | None = None
    expect_ai_generation: bool = False

    @property
    def local_media(self) -> bool:
        """Built from samples/ (real third-party posts, gitignored)."""
        return str(self.input.get("file") or "").startswith("samples/")


@dataclass
class Outcome:
    case: Case
    status: str            # PASS | FAIL | SKIP | ERROR
    label: str = "-"
    language: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    reasons: list[str] | None = None
    gold: str = "-"        # page | site | no | - (no gold given)
    cache: str = "-"


def load_cases(match: str | None = None) -> list[Case]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        c = Case(id=raw["id"], input=raw["input"], language=str(raw["language"]),
                 expected=[_label(x) for x in raw["expected"]], budget_s=raw.get("budget_s"), case=raw.get("case"),
                 gold=list(raw.get("gold") or []), after=raw.get("after"), expect_cache=raw.get("expect_cache"),
                 expect_ai_generation=bool(raw.get("expect_ai_generation")))
        cases.append(c)
    if match:
        # Keep the cases a selected case depends on (after:), so a chain runs whole.
        chosen = {c.id for c in cases if match in c.id}
        by_id = {c.id: c for c in cases}
        for cid in list(chosen):
            while by_id[cid].after and by_id[cid].after in by_id:
                cid = by_id[cid].after
                chosen.add(cid)
        cases = [c for c in cases if c.id in chosen]
    return cases


def _norm_url(url: str) -> tuple[str, str]:
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    return host, f"{host}{p.path.rstrip('/')}".lower()


def gold_match(gold: list[str], cited_urls: list[str]) -> str:
    """page: a gold fact check itself was cited; site: another page from a gold publisher; no: neither."""
    if not gold:
        return "-"
    got = [_norm_url(u) for u in cited_urls if u]
    want = [_norm_url(u) for u in gold]
    if {p for _, p in got} & {p for _, p in want}:
        return "page"
    if {h for h, _ in got} & {h for h, _ in want}:
        return "site"
    return "no"


def _label(x: object) -> str:
    # Unquoted TRUE/FALSE in YAML parse as booleans.
    return str(x).upper()


def same_language(actual: str | None, expected: str) -> bool:
    return bool(actual) and actual.split("-")[0].lower() == expected.split("-")[0].lower()


async def run_case(case: Case, runs_dir: Path, record: bool, store=None) -> Outcome:
    """`store`: shared with the case this one runs after (tier 1 re-share tests)."""
    from app.agents.tools import RecordingTools, Tools
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
    if file and not Path(file).exists():  # noqa: ASYNC240  dev tool, one local file
        return Outcome(case, "SKIP", reasons=[f"{inp['file']} not present (samples/ is local only)"])
    try:
        req, _keys, _notes = await harness.build_request(inp.get("text"), file, inp.get("url"))
    except (InvalidInput, OSError) as e:
        return Outcome(case, "ERROR", reasons=[f"bad input: {e}"])

    # Fresh memory store per case unless it is part of a chain: acceptance measures the pipeline.
    chained = store is not None
    store = store if chained else MemoryStore()
    recording = record and not case.local_media and not case.after
    tools = RecordingTools(Tools(store)) if recording else None
    run, captured = await harness.run(req, store=store, llm=get_llm(), tools=tools, cache_keys=_keys,
                                      tier1=chained)
    harness.save_run(run, runs_dir, case.id)
    if recording and not run.error:
        captured.save(case.id, tools.calls if tools else None)

    budget = case.budget_s or harness.total_budget_s(req)
    reasons = []
    if run.error:
        reasons.append(f"error {run.error}")
    # The primary claim decides; secondary claims are shown in the table but may legitimately differ
    # (a news link also mentions things nobody has checked).
    if run.primary_label not in case.expected:
        reasons.append(f"label {run.primary_label}, want {'|'.join(case.expected)}")
    if not same_language(run.language, case.language):
        reasons.append(f"language {run.language}, want {case.language}")
    if run.latency_ms > budget * 1000:
        reasons.append(f"latency {run.latency_ms / 1000:.1f}s > {budget:.0f}s")
    claims = run.result.claims if run.result else []
    tier = run.result.cache_tier_hit if run.result else "-"
    if case.expect_cache and tier != case.expect_cache:
        reasons.append(f"cache {tier}, want {case.expect_cache}")
    if case.expect_ai_generation and not (claims and claims[0].ai_generation):
        reasons.append("no AI-generation assessment")
    gold = gold_match(case.gold, [e.url for c in claims for e in c.evidence if e.url])
    return Outcome(case, "FAIL" if reasons else "PASS", run.label, run.language, run.latency_ms,
                   run.ledger.total_cost_usd, reasons, gold, tier)


def print_table(outcomes: list[Outcome]) -> None:
    color = {"PASS": GREEN, "FAIL": RED, "ERROR": RED, "SKIP": YELLOW}
    w = max(len(o.case.id) for o in outcomes)
    print(f"\n{BOLD}{'case':<{w}}  {'result':<6}  {'label':<20}  {'lang':<6}  {'cache':<5}  {'gold':<5}  "
          f"{'latency':>8}  {'cost':>9}  why{RESET}")
    for o in outcomes:
        lang_ok = same_language(o.language, o.case.language)
        lang = f"{o.language or '-'}" + ("" if lang_ok or o.status == "SKIP" else "!")
        print(f"{o.case.id:<{w}}  {color[o.status]}{o.status:<6}{RESET}  {o.label:<20}  {lang:<6}  {o.cache:<5}  "
              f"{o.gold:<5}  {o.latency_ms / 1000:>7.1f}s  ${o.cost_usd:>8.5f}  "
              f"{DIM}{'; '.join(o.reasons or [])}{RESET}")
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

    # Chains (after:) run in order in one shared store; independent chains run concurrently.
    by_parent: dict[str, list[Case]] = {}
    for c in cases:
        if c.after:
            by_parent.setdefault(c.after, []).append(c)
    ids = {c.id for c in cases}

    async def chain(root: Case) -> list[Outcome]:
        from app.store import MemoryStore

        store = MemoryStore() if root.id in by_parent else None
        out, todo = [], [root]
        while todo:
            c = todo.pop(0)
            async with sem:
                try:
                    o = await run_case(c, runs_dir, a.record, store)
                except Exception as e:  # noqa: BLE001  a crashed case must not hide the others
                    o = Outcome(c, "ERROR", reasons=[repr(e)[:200]])
            print(f"  {o.status:<5} {c.id}  {o.latency_ms / 1000:.1f}s", flush=True)
            out.append(o)
            todo += by_parent.get(c.id, [])
        return out

    roots = [c for c in cases if not c.after or c.after not in ids]
    order = {c.id: i for i, c in enumerate(cases)}
    outcomes = sorted((o for group in await asyncio.gather(*(chain(r) for r in roots)) for o in group),
                      key=lambda o: order[o.case.id])
    print_table(outcomes)
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "summary.json").write_text(json.dumps([{
        "id": o.case.id, "status": o.status, "label": o.label, "expected": o.case.expected,
        "language": o.language, "expected_language": o.case.language, "latency_ms": o.latency_ms,
        "cost_usd": o.cost_usd, "reasons": o.reasons or [], "gold": o.gold, "cache": o.cache,
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
