"""Eval runner (Cloud Run Job `eval-runner`, every 3 days; docs/10). `make eval` runs it locally.

1. Cross-lingual recall at 5: each benchmark claim is restated in another language (Flash), then only the
   fact-check sites agent's retrieval runs (search_plan + Fact Check Tools API). Hit if the original
   fact check URL is in the first 5 results.
2. Verdict regression: the full pipeline on gold claims (published ratings) plus silver claims (our own
   production verdicts the panel AGREED on with HIGH confidence and a TIER_1 source), cache bypassed.
3. One row in BigQuery `eval_runs`, per-item details in gs://{project}-eval/runs/{run_id}.json.
4. Drift against the baseline run: recall at 5 or verdict agreement down more than 5 points, or p95
   latency up more than 30%: drift_flag, an ERROR log line (alert policy emails Rohit) and
   Firestore config/flags.model_review_needed = true.

The pipeline runs on an overlay store: reads of the offender list (`sources`) go to Firestore, everything
else (checks, verdicts, cache) stays in memory, so the eval never reads or writes the production cache.
Pipeline runs do not write check_runs/model_calls (they would mix eval traffic into production metrics).

Default size is docs/10's: 200 recall claims, 60 gold, 30 silver. Measured Oct 9: about 0.11 US dollars per
pipeline item (audio off), so 7 to 10 dollars a run. Smaller:  make eval ARGS="--gold-n 10 --silver-n 0"
Model swap test (no config change):  make eval ARGS="--candidate pro=gemini-3-pro --label candidate"
"""
from __future__ import annotations

import os

os.environ["BIGQUERY_ENABLED"] = "0"  # pipeline runs must not write production check_runs (see docstring)
os.environ["TTS_ENABLED"] = "0"       # audio is not evaluated here; it would add cost and 20 s per item

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from dataclasses import asdict, dataclass, field  # noqa: E402
from datetime import UTC, date, datetime  # noqa: E402
from typing import Any  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from app.models import RegionalQuery  # noqa: E402
from eval import datasets  # noqa: E402

log = logging.getLogger("eval")
DECISIVE_NEGATIVE = {"FALSE", "MISLEADING", "SCAM"}
# Benchmark language -> language the claim is restated in (a forward retold in another language).
PAIRS = {"hi": "ta", "ta": "kn", "kn": "hi", "en": "hi", "id": "en"}
LANGUAGE_NAMES = {"hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "id": "Indonesian", "en": "English"}
DRIFT_POINTS = 5.0
DRIFT_LATENCY = 0.30
MEDIA_TYPES = {"MEDIA_AUTHENTICITY"}  # silver claims about a photo or video cannot be re-run from text


class EvalQuery(BaseModel):
    claim_original: str
    claim_en: str
    search_queries_original: list[str] = []
    search_queries_en: list[str] = []
    search_queries_regional: list[RegionalQuery] = []


# ---------- overlay store ----------

class OverlayStore:
    """Memory store that reads selected collections through from Firestore (never writes there)."""

    def __init__(self, read_through: set[str]) -> None:
        from app.store import FirestoreStore, MemoryStore

        self.mem = MemoryStore()
        self.fs = FirestoreStore()
        self.read_through = read_through

    async def get(self, collection: str, doc_id: str):
        doc = await self.mem.get(collection, doc_id)
        if doc is None and collection in self.read_through:
            return await self.fs.get(collection, doc_id)
        return doc

    def __getattr__(self, name: str):
        return getattr(self.mem, name)


# ---------- 1. recall at 5 ----------

async def top_urls(llm, tools, item: dict, target: str) -> list[str]:
    """The first 15 fact-check URLs our retrieval returns for the claim restated in `target` (the agent shows
    its classifier up to 15, factcheck_sites.MAX_REVIEWS; recall at 5 uses the first 5)."""
    from app.agents import factcheck_sites
    from app.models import Claim, ClaimType, Extraction, TimeSensitivity
    from app.prompts import load_prompt

    p = load_prompt("12_eval_query.md")
    text = p.render(target_language=target, target_language_name=LANGUAGE_NAMES[target],
                    source_language=LANGUAGE_NAMES[item["language"]], claim_text=item["claim_text"])
    q = await llm.generate(stage="eval_query", prompt=text, prompt_version=p.version, schema=EvalQuery,
                           timeout_s=30)
    ext = Extraction(
        content_language=target, content_script="Zyyy", summary_en="", checkable=True,
        claims=[Claim(claim_id="c1", claim_original=q.claim_original, claim_en=q.claim_en,
                      claim_type=ClaimType.EVENT, time_sensitivity=TimeSensitivity.EVERGREEN,
                      search_queries_original=q.search_queries_original[:3],
                      search_queries_en=q.search_queries_en[:3],
                      search_queries_regional=q.search_queries_regional[:3])])
    batches = await asyncio.gather(*(tools.factcheck_search(qq, lang)
                                     for qq, lang in factcheck_sites.search_plan(ext)))
    urls: list[str] = []
    for batch in batches:  # the agent's own order: plan order, then the API's ranking
        for r in batch:
            u = datasets.norm_url(r.get("url"))
            if u and u not in urls:
                urls.append(u)
    return urls[:15]


async def recall_at_5(llm, tools, items: list[dict], jobs: int) -> tuple[dict, list[dict]]:
    sem = asyncio.Semaphore(jobs)
    rows: list[dict] = []

    async def one(item: dict) -> None:
        target = PAIRS[item["language"]]
        async with sem:
            try:
                urls = await top_urls(llm, tools, item, target)
                rank, err = _rank(urls, item["url"]), None
            except Exception as e:  # noqa: BLE001  a failed item counts as a miss, and is reported
                urls, rank, err = [], None, f"{type(e).__name__}: {str(e)[:120]}"
        rows.append({"id": item["id"], "pair": f"{item['language']}->{target}", "hit": rank is not None and rank < 5,
                     "hit15": rank is not None, "rank": rank, "top15": urls, "error": err})

    await asyncio.gather(*(one(i) for i in items))
    out: dict[str, Any] = {"overall": _rate([r["hit"] for r in rows]), "n": len(rows),
                           "at_15": _rate([r["hit15"] for r in rows])}
    for pair in sorted({r["pair"] for r in rows}):
        out[pair] = _rate([r["hit"] for r in rows if r["pair"] == pair])
    return out, rows


# ---------- 2. verdict regression ----------

@dataclass
class VerdictRow:
    id: str
    set: str               # gold or silver
    language: str
    expected: str
    got: str
    latency_ms: int
    cost_usd: float
    panel_outcome: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def stable_mix(items: list[dict]) -> list[dict]:
    """Round-robin across languages in dataset order: the first N gold items are the same N every run
    (needed to compare with the baseline) and cover every language."""
    by_lang: dict[str, list[dict]] = {}
    for i in items:
        by_lang.setdefault(i["language"], []).append(i)
    out: list[dict] = []
    while any(by_lang.values()):
        for lang in datasets.LANGUAGES + sorted(set(by_lang) - set(datasets.LANGUAGES)):
            if by_lang.get(lang):
                out.append(by_lang[lang].pop(0))
    return out


def silver_items(n: int, rng: random.Random) -> list[dict]:
    """Production verdicts the panel AGREED on, HIGH band, at least one cited TIER_1 source, text claims."""
    if n <= 0:
        return []
    from google.cloud import firestore

    from app.settings import get_settings

    s = get_settings()
    db = firestore.Client(project=s.gcp_project, database=s.firestore_db)
    q = (db.collection("verdicts").where(filter=firestore.FieldFilter("panel_outcome", "==", "AGREED"))
         .where(filter=firestore.FieldFilter("band", "==", "HIGH")).limit(400))
    pool = []
    for snap in q.stream():
        d = snap.to_dict()
        cited = set(d.get("evidence_for_ids") or []) | set(d.get("evidence_against_ids") or [])
        tier1 = any(e.get("tier") == "TIER_1" and e.get("evidence_id") in cited for e in d.get("evidence") or [])
        if tier1 and d.get("claim_type") not in MEDIA_TYPES and d.get("claim_original"):
            pool.append({"id": snap.id, "claim_text": d["claim_original"], "label": d["label"],
                         "language": (d.get("content_language") or "en").split("-")[0]})
    rng.shuffle(pool)
    return pool[:n]


async def verdicts(llm, items: list[dict], jobs: int) -> list[VerdictRow]:
    from app.agents.tools import default_tools
    from app.devtools import harness

    sem = asyncio.Semaphore(jobs)
    rows: list[VerdictRow] = []

    async def one(item: dict) -> None:
        async with sem:
            store = OverlayStore({"sources"})
            try:
                req, _, _ = await harness.build_request(text=item["claim_text"])
                run, _ = await harness.run(req, store=store, llm=llm, tools=default_tools(store))
                outcome = run.result.claims[0].panel_outcome.value if run.result and run.result.claims else None
                rows.append(VerdictRow(item["id"], item["set"], item["language"], item["label"], run.primary_label,
                                       run.latency_ms, run.ledger.total_cost_usd, outcome, run.error, run.notes))
            except Exception as e:  # noqa: BLE001
                rows.append(VerdictRow(item["id"], item["set"], item["language"], item["label"], "ERROR", 0, 0.0,
                                       error=f"{type(e).__name__}: {str(e)[:200]}"))

    await asyncio.gather(*(one(i) for i in items))
    return rows


def verdict_metrics(rows: list[VerdictRow]) -> dict[str, Any]:
    """Strict: same label. Direction: both say "do not believe this" (FALSE, MISLEADING or SCAM) or both
    TRUE; fact-checkers' ratings and our 5 labels cut FALSE and MISLEADING differently."""
    done = [r for r in rows if r.got not in ("ERROR", "FAILED", "-")]
    answered = [r for r in done if r.got != "NOT_ENOUGH_EVIDENCE"]
    lat = sorted(r.latency_ms for r in done) or [0]

    def direction(r: VerdictRow) -> bool:
        return r.got == r.expected or (r.got in DECISIVE_NEGATIVE and r.expected in DECISIVE_NEGATIVE)

    return {
        "verdict_agreement": _rate([r.got == r.expected for r in rows]),
        "direction_agreement": _rate([direction(r) for r in rows]),
        "abstain_rate": _rate([r.got == "NOT_ENOUGH_EVIDENCE" for r in done]),
        "accuracy_when_answered": _rate([r.got == r.expected for r in answered]),
        "panel_agreed_rate": _rate([r.panel_outcome in ("AGREED", "AGREED_AFTER_REVISION") for r in done]),
        "p50_latency_ms": int(statistics.median(lat)),
        "p95_latency_ms": int(lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]),
        "cost_per_check": round(sum(r.cost_usd for r in done) / max(1, len(done)), 5),
        "errors": len(rows) - len(done),
    }


def _rank(urls: list[str], target: str) -> int | None:
    u = datasets.norm_url(target)
    return urls.index(u) if u in urls else None


def _rate(xs: list[bool]) -> float | None:
    return round(100.0 * sum(xs) / len(xs), 1) if xs else None


# ---------- 3 and 4. baseline, drift, storage ----------

def drift(current: dict, baseline: dict | None) -> list[str]:
    """Reasons this run drifted from the baseline (empty list: no drift)."""
    if not baseline:
        return []
    reasons = []
    cur_r = (current.get("recall_at_5") or {}).get("overall")
    base_r = (baseline.get("recall_at_5") or {}).get("overall")
    if cur_r is not None and base_r is not None and base_r - cur_r > DRIFT_POINTS:
        reasons.append(f"recall at 5 {base_r} -> {cur_r}")
    for k in ("verdict_agreement", "direction_agreement"):
        c, b = current.get(k), baseline.get(k)
        if c is not None and b is not None and b - c > DRIFT_POINTS:
            reasons.append(f"{k} {b} -> {c}")
    c, b = current.get("p95_latency_ms"), baseline.get("p95_latency_ms")
    if c and b and c > b * (1 + DRIFT_LATENCY):
        reasons.append(f"p95 latency {b} ms -> {c} ms")
    return reasons


def _flags_doc():
    from google.cloud import firestore

    from app.settings import get_settings

    s = get_settings()
    return firestore.Client(project=s.gcp_project, database=s.firestore_db).collection("config")


def baseline_row(baseline_id: str | None) -> dict | None:
    if not baseline_id:
        return None
    from google.cloud import bigquery

    from app.settings import get_settings

    s = get_settings()
    q = f"SELECT * FROM `{s.gcp_project}.{s.bigquery_dataset}.eval_runs` WHERE run_id = @id LIMIT 1"
    job = bigquery.Client(project=s.gcp_project).query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", baseline_id)]))
    for r in job.result():
        row = dict(r)
        if isinstance(row.get("recall_at_5"), str):
            row["recall_at_5"] = json.loads(row["recall_at_5"])
        return row
    return None


def write_row(row: dict) -> None:
    from google.cloud import bigquery

    from app.observability.bq_schemas import ensure_eval_table
    from app.settings import get_settings

    s = get_settings()
    ensure_eval_table()
    out = {k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in row.items()}
    errors = bigquery.Client(project=s.gcp_project).insert_rows_json(
        f"{s.gcp_project}.{s.bigquery_dataset}.eval_runs", [out])
    if errors:
        raise RuntimeError(f"eval_runs insert failed: {errors}")


def save_details(run_id: str, details: dict) -> str:
    from google.cloud import storage

    name = f"runs/{run_id}.json"
    storage.Client().bucket(datasets._bucket()).blob(name).upload_from_string(
        json.dumps(details, ensure_ascii=False, indent=1, default=str), content_type="application/json")
    return f"gs://{datasets._bucket()}/{name}"


def apply_candidates(candidates: list[str]) -> dict[str, str]:
    """--candidate flash=<model_id>: run this eval with another model for that alias (no config change)."""
    from app.settings import get_config

    models = get_config().models["models"]
    out = {}
    for c in candidates:
        alias, _, model_id = c.partition("=")
        if alias not in models or not model_id:
            raise SystemExit(f"--candidate {c}: alias must be one of {', '.join(models)}")
        models[alias]["id"] = model_id
        out[alias] = model_id
    return out


async def run(a: argparse.Namespace) -> int:
    from app.agents.tools import default_tools
    from app.llm import get_llm
    from app.prompts import load_prompt
    from app.settings import get_config

    candidates = apply_candidates(a.candidate)
    version = a.dataset or datasets.latest_version()
    rng = random.Random(a.seed)
    run_id = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{a.label}"
    llm = get_llm()
    t0 = time.monotonic()

    bench = stable_mix(datasets.load(version, "benchmark.jsonl"))[: a.recall_n]
    recall, recall_rows = (await recall_at_5(llm, default_tools(OverlayStore(set())), bench, a.jobs)
                           if bench and a.recall_n else ({}, []))
    print(f"recall at 5: {recall}")

    gold = stable_mix([dict(g, set="gold") for g in datasets.load(version, "gold.jsonl")])
    items = gold[: a.gold_n] + [dict(s, set="silver") for s in silver_items(a.silver_n, rng)]
    vrows = await verdicts(llm, items, a.jobs) if items else []
    vm = verdict_metrics(vrows) if vrows else {}
    for st in ("gold", "silver"):
        sub = [r for r in vrows if r.set == st]
        if sub:
            m = verdict_metrics(sub)
            print(f"{st}: n={len(sub)} strict {m['verdict_agreement']}% direction {m['direction_agreement']}% "
                  f"abstain {m['abstain_rate']}% p95 {m['p95_latency_ms']} ms ${m['cost_per_check']}/check")

    cfg = get_config()
    flags = _flags_doc()
    baseline_id = None if a.set_baseline else (flags.document("eval").get().to_dict() or {}).get("baseline_run_id")
    current = {"recall_at_5": recall, **vm}
    reasons = drift(current, baseline_row(baseline_id))
    total_cost = round(sum(r.cost_usd for r in vrows), 4)
    details_uri = save_details(run_id, {
        "run_id": run_id, "dataset_version": version, "candidates": candidates, "metrics": current,
        "drift": reasons, "recall_rows": recall_rows, "verdict_rows": [asdict(r) for r in vrows],
    })
    row = {
        "run_id": run_id, "run_at": datetime.now(UTC).isoformat(),
        "model_config": {k: v["id"] for k, v in cfg.models["models"].items()},
        "prompt_versions": {n: load_prompt(n).version for n in
                            ("01_extractor.md", "03_web_search_agent.md", "04_factcheck_agent.md", "08_judge.md",
                             "09_critic.md", "10_composer.md")},
        "recall_at_5": recall, "verdict_agreement": vm.get("verdict_agreement"),
        "direction_agreement": vm.get("direction_agreement"), "abstain_rate": vm.get("abstain_rate"),
        "accuracy_when_answered": vm.get("accuracy_when_answered"),
        "p50_latency_ms": vm.get("p50_latency_ms"), "p95_latency_ms": vm.get("p95_latency_ms"),
        "cost_per_check": vm.get("cost_per_check"), "total_cost_usd": total_cost,
        "n_recall": len(recall_rows), "n_gold": sum(r.set == "gold" for r in vrows),
        "n_silver": sum(r.set == "silver" for r in vrows), "dataset_version": version,
        "label": a.label, "details_uri": details_uri,
        "baseline_run_id": baseline_id, "drift_flag": bool(reasons),
    }
    write_row(row)
    if a.set_baseline:
        flags.document("eval").set({"baseline_run_id": run_id, "set_at": date.today().isoformat()}, merge=True)
    if reasons and not candidates:
        log.error("eval drift: %s", "; ".join(reasons))
        flags.document("flags").set({"model_review_needed": True, "reason": "; ".join(reasons),
                                     "run_id": run_id}, merge=True)
    base = "this run" if a.set_baseline else baseline_id
    print(f"{run_id}: drift={reasons or 'none'} baseline={base}  {time.monotonic() - t0:.0f} s  ${total_cost}  "
          f"details {details_uri}")
    return 0


def main() -> int:
    from app.observability.logging import setup_logging

    setup_logging()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset", help="dataset version (default: the latest in the eval bucket)")
    ap.add_argument("--recall-n", type=int, default=200)
    ap.add_argument("--gold-n", type=int, default=60)
    ap.add_argument("--silver-n", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=2, help="concurrent pipeline runs (3+ hit Vertex 429s, Oct 8)")
    ap.add_argument("--seed", type=int, default=int(date.today().strftime("%Y%m%d")))
    ap.add_argument("--candidate", action="append", default=[], help="alias=model_id, e.g. pro=gemini-3-pro")
    ap.add_argument("--label", default="scheduled")
    ap.add_argument("--set-baseline", action="store_true", help="make this run the baseline for drift")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
