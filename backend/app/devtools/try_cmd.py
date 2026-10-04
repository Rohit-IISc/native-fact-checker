"""make try TEXT="..." | FILE=path | URL=...  [STAGE=extract] [STORE=firestore] [FAKE=1]

Runs the real pipeline in-process and prints each stage with its time, the claims, the evidence
with tiers, the panel outcome, the answer in the content language, and the cost. Every run is
saved to runs/{timestamp}.json (gitignored).

Default store is in-memory (no writes to the dev Firestore DB, no shared cache). Pass
--store firestore to exercise the real cache and progress docs.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / "runs"

DIM, BOLD, RED, GREEN, YELLOW, CYAN, RESET = (
    ("\033[2m", "\033[1m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m")
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR") else ("",) * 7
)
LABEL_COLOR = {"TRUE": GREEN, "FALSE": RED, "MISLEADING": YELLOW, "SCAM": RED}


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="make try", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--text")
    p.add_argument("--file")
    p.add_argument("--url")
    p.add_argument("--stage", choices=["full", "extract"], default="full")
    p.add_argument("--store", choices=["memory", "firestore"], default="memory")
    p.add_argument("--fake", action="store_true", help="LLM_MODE=fake: canned outputs, no paid calls")
    p.add_argument("--json", action="store_true", help="print the saved run JSON instead of the report")
    a = p.parse_args(argv)
    if not (a.text or a.file or a.url):
        p.error('give one of TEXT="...", FILE=path or URL=...')
    return a


def _wrap(text: str, indent: int = 4) -> str:
    return textwrap.fill(text, width=100, initial_indent=" " * indent, subsequent_indent=" " * indent)


def print_report(run, saved: Path) -> None:
    # Stage lines were already streamed as each stage ended (see on_stage).
    print(f"  {BOLD}total {run.latency_ms} ms{RESET}")

    ex = run.extraction
    if ex is not None:
        print(f"\n{BOLD}Extraction{RESET}  language={ex.content_language} script={ex.content_script} "
              f"checkable={ex.checkable}" + (f" type={ex.non_checkable_type.value}" if ex.non_checkable_type else ""))
        print(_wrap(ex.summary_en))
        for c in ex.claims:
            print(f"  {CYAN}{c.claim_id}{RESET} [{c.claim_type.value}, {c.time_sensitivity.value}]")
            print(_wrap(f"original: {c.claim_original}", 6))
            print(_wrap(f"english:  {c.claim_en}", 6))
            if c.search_queries_en:
                print(_wrap(f"queries:  {' | '.join(c.search_queries_en)}", 6))
        for extra in ex.extra_claims_not_checked:
            print(f"  {DIM}not checked: {extra}{RESET}")

    res = run.result
    if res is not None:
        if res.non_checkable_type:
            print(f"\n{BOLD}Result{RESET}  NOT_CHECKABLE ({res.non_checkable_type.value})")
            print(_wrap(res.non_checkable_message or ""))
        for cr in res.claims:
            color = LABEL_COLOR.get(cr.label.value, YELLOW)
            print(f"\n{BOLD}Claim {cr.verdict_id}{RESET}  {color}{BOLD}{cr.label.value}{RESET}  "
                  f"confidence={cr.confidence} ({cr.band})  panel={cr.panel_outcome.value}")
            print(f"  {BOLD}Evidence{RESET} ({len(cr.evidence)})")
            if not cr.evidence:
                print(f"    {DIM}none{RESET}")
            for e in cr.evidence:
                side = "for" if e.evidence_id in cr.evidence_for_ids else (
                    "against" if e.evidence_id in cr.evidence_against_ids else "-")
                print(f"    {e.evidence_id:<6} {e.tier.value:<8} {e.stance.value:<12} {side:<8} "
                      f"{e.publisher or ''} {DIM}{e.url or ''}{RESET}")
            a = cr.answer
            print(f"  {BOLD}Answer ({a.language}){RESET}")
            print(_wrap(f"{BOLD}{a.headline}{RESET}"))
            print(_wrap(a.summary))
            print(_wrap(f"{DIM}audio: {a.audio_script}{RESET}"))
            if not a.language.startswith("en"):
                print(f"  {BOLD}Answer (en){RESET}")
                print(_wrap(cr.answer_en.headline))
            print(f"  {DIM}result page: {cr.result_url}{RESET}")

    if run.error:
        print(f"\n{RED}{BOLD}Error:{RESET} {run.error}")
    for n in run.notes:
        print(f"{YELLOW}note:{RESET} {n}")

    led = run.ledger
    print(f"\n{BOLD}Cost{RESET}  ${led.total_cost_usd:.5f} total (models ${led.model_cost_usd:.5f}, "
          f"{led.grounding_queries} grounding queries)")
    for c in led.calls:
        flag = "" if c.success else f" {RED}FAILED{RESET}"
        print(f"  {c.stage:<12} {c.model_id:<26} in={c.input_tokens:<6} out={c.output_tokens:<5} "
              f"think={c.thinking_tokens:<5} {c.latency_ms:>6} ms  ${c.cost_usd:.5f}{flag}")
    print(f"\n{DIM}saved {saved.relative_to(ROOT)}{RESET}")


async def amain(a: argparse.Namespace) -> int:
    os.environ["STORE"] = a.store
    if a.fake:
        os.environ["LLM_MODE"] = "fake"
    os.environ.setdefault("PIPELINE_MODE", "inline")

    from app.devtools import harness
    from app.intake.validate import InvalidInput
    from app.llm import get_llm
    from app.observability.logging import setup_logging
    from app.settings import get_settings
    from app.store import get_store

    setup_logging(logging.WARNING)  # the report already shows every model call
    s = get_settings()
    try:
        req, keys, notes = await harness.build_request(a.text, a.file, a.url)
    except InvalidInput as e:
        print(f"{RED}invalid input:{RESET} {e.error_code}: {e.message}")
        return 2
    print(f"{DIM}check {req.check_id}  llm={s.llm_mode}  store={s.store}"
          f"{'/' + s.firestore_db if s.store == 'firestore' else ''}  project={s.gcp_project}  "
          f"budget={harness.total_budget_s(req):.0f}s{RESET}")

    def on_stage(st):
        if not a.json:
            print(f"  {DIM}{st.started_s:6.2f}s{RESET}  {st.stage:<14} {st.duration_ms:>6} ms", flush=True)

    run, _ = await harness.run(req, store=get_store(), llm=get_llm(), stage=a.stage,
                               cache_keys=keys if a.store == "firestore" else [], on_stage=on_stage)
    run.notes += notes
    saved = harness.save_run(run, RUNS_DIR)
    if a.json:
        print(saved.read_text(encoding="utf-8"))
    else:
        print_report(run, saved)
    return 1 if run.error else 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(asyncio.run(amain(parse(argv))))


if __name__ == "__main__":
    main()
