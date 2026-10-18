"""Replay the evidence score (decision 50) on stored verdicts. No LLM calls; embeddings only (for grouping).

Sources:
  - production verdicts (Firestore "(default)") and dev verdicts ("dev-db"), with each check's source
    assessment for repeat-offender and young domains;
  - every saved acceptance run (runs/accept-*/**.json), whose cases carry expected labels (our gold set with
    stored evidence; the 57-item eval gold set runs on an in-memory store and keeps no evidence).

Writes runs/replay-evidence-score-<time>.json and prints a markdown report. Usage (from backend/):
  PYTHONPATH=.:.. uv run python ../scripts/replay_evidence_score.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.devtools.accept import load_cases
from app.llm import get_llm
from app.models import Evidence, JudgeVerdict, Label
from app.verify import source_policy as sp
from app.verify.source_tiers import host_of

ROOT = Path(__file__).resolve().parent.parent
_embed_cache: dict[str, list[float]] = {}
RUNS_GLOB = "accept-*"


async def embed(texts: list[str]) -> list[list[float]]:
    todo = [t for t in texts if t not in _embed_cache]
    if todo:
        vecs = await get_llm().embed(todo, timeout_s=20)
        _embed_cache.update(zip(todo, vecs, strict=True))
    return [_embed_cache[t] for t in texts]


def discounted(assessment: dict | None) -> set[str]:
    a = assessment or {}
    young = a.get("domain_age_days") is not None and a["domain_age_days"] < 90
    if (a.get("repeat_offender_count") or 0) > 0 or young:
        host = host_of(a.get("origin_name") or "")
        return {host} if host else set()
    return set()


async def score_one(source: str, ref: str, label: str, outcome: str | None, claim_type: str | None, claim_en: str,
                    evidence: list[dict], for_ids: list[str], against: list[str], expected: list[str] | None,
                    disc: set[str]) -> dict:
    ev = [Evidence.model_validate(e) for e in evidence]
    v = JudgeVerdict(claim_id="c", label=Label(label), confidence=0, what_is_true_en="", evidence_for_ids=for_ids,
                     evidence_against_ids=against, cited_ids=[], reasoning_en="")
    s = await sp.evidence_score(v, ev, claim_type=claim_type, claim_en=claim_en, discounted_domains=disc,
                                embed=embed)
    d = sp.gate(Label(label), s)
    by_id = {e.evidence_id: e for e in ev}
    return {
        "source": source, "ref": ref, "claim_en": claim_en, "claim_type": claim_type, "label": label,
        "panel_outcome": outcome, "expected": expected, "score": round(s.score, 2), "p_true": round(s.p_true, 3),
        "high_harm": s.high_harm, "cutoff": s.cutoff, "score_label": s.score_label.value, "action": d.action,
        "proposed": d.proposed.value if d.proposed else None, "would_be": d.label.value,
        "groups_for": s.groups_for, "groups_against": s.groups_against,
        "strong_against": s.strong_against,
        "items": [{"id": i.evidence_id, "dir": i.direction, "w": i.weight, "why": i.why,
                   "publisher": by_id[i.evidence_id].publisher, "tier": by_id[i.evidence_id].tier.value,
                   "title": (by_id[i.evidence_id].title or "")[:90]} for i in s.items],
    }


async def from_firestore(db_name: str) -> list[dict]:
    from google.cloud import firestore

    from app.settings import get_settings

    db = firestore.Client(project=get_settings().gcp_project, database=db_name)
    rows = []
    for doc in db.collection("verdicts").stream():
        v = doc.to_dict()
        if v.get("is_stub"):
            continue
        chk = db.collection("checks").document(v.get("check_id") or "-").get()
        assessment = (chk.to_dict() or {}).get("source_assessment") if chk.exists else None
        rows.append(await score_one(f"firestore:{db_name}", doc.id, v["label"], v.get("panel_outcome"),
                                    v.get("claim_type"), v.get("claim_en") or "", v.get("evidence") or [],
                                    v.get("evidence_for_ids") or [], v.get("evidence_against_ids") or [], None,
                                    discounted(assessment)))
    return rows


async def from_accept_runs() -> list[dict]:
    cases = {c.id: c for c in load_cases()}
    rows = []
    for path in sorted((ROOT / "runs").glob(f"{RUNS_GLOB}/**/*.json")):
        m = re.match(r"\d{8}-\d{6}-(.+)\.json$", path.name)
        case = cases.get(m.group(1)) if m else None
        if not case:
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        result = run.get("result") or {}
        claims = {c["claim_id"]: c for c in (run.get("extraction") or {}).get("claims") or []}
        for i, c in enumerate(result.get("claims") or []):
            ex = next((x for x in claims.values() if x.get("claim_en") == c.get("claim_en")), None) or {}
            expected = case.expected if i == 0 else None  # expected labels describe the post's main claim
            rows.append(await score_one("accept", f"{path.parent.name}/{path.name}", c["label"], c.get("panel_outcome"),
                                        ex.get("claim_type"), c.get("claim_en") or "", c.get("evidence") or [],
                                        c.get("evidence_for_ids") or [], c.get("evidence_against_ids") or [],
                                        expected, set()))
    return rows


def report(rows: list[dict]) -> str:
    out = []
    by_src = Counter(r["source"] for r in rows)
    out.append(f"Scored {len(rows)} verdicts: " + ", ".join(f"{k} {v}" for k, v in by_src.items()))
    acts = Counter((r["source"].split(":")[0], r["action"], r["proposed"]) for r in rows)
    out.append("\n| source | action | proposed | count |\n|---|---|---|---|")
    for (src, act, prop), n in sorted(acts.items()):
        out.append(f"| {src} | {act} | {prop or ''} | {n} |")
    gold = [r for r in rows if r["expected"]]
    out.append(f"\nGold (acceptance runs with expected labels): {len(gold)} main claims")
    changed = [r for r in gold if r["action"] in ("blocked", "to_critic")]
    fix = sum(r["action"] == "to_critic" and r["proposed"] in r["expected"] for r in changed)
    harm = sum(r["action"] == "to_critic" and r["proposed"] not in r["expected"] for r in changed)
    wrong_now = [r for r in gold if r["label"] not in r["expected"]]
    out.append(f"- currently wrong against gold: {len(wrong_now)}")
    out.append(f"- changes to answers that are right today: {sum(r['label'] in r['expected'] for r in changed)}")
    out.append(f"- NEE sent to Critic for TRUE where gold is TRUE (fix): {fix}; where it is not (would be wrong "
               f"if the Critic accepts): {harm}")
    out.append("\nEvery change against gold:\n\n| run | judge label | expected | score | p(true) | action | proposed |"
               "\n|---|---|---|---|---|---|---|")
    for r in changed:
        out.append(f"| {r['ref']} | {r['label']} | {'/'.join(r['expected'])} | {r['score']} | {r['p_true']} | "
                   f"{r['action']} | {r['proposed'] or ''} |")
    out.append("\nProduction and dev verdicts that would change:\n\n| verdict | label | claim | score | p(true) | "
               "action | proposed |\n|---|---|---|---|---|---|---|")
    for r in rows:
        if r["source"].startswith("firestore") and r["action"] in ("blocked", "to_critic"):
            out.append(f"| {r['ref'][:10]} | {r['label']} | {r['claim_en'][:70]} | {r['score']} | {r['p_true']} | "
                       f"{r['action']} | {r['proposed'] or ''} |")
    return "\n".join(out)


async def main() -> int:
    import argparse

    from app.settings import get_config

    ap = argparse.ArgumentParser()
    ap.add_argument("--similarity", type=float, help="override same_origin_similarity (sensitivity runs)")
    ap.add_argument("--runs", default="accept-*", help="glob of run folders under runs/")
    a = ap.parse_args()
    if a.similarity:
        get_config().source_tiers["evidence_score"]["same_origin_similarity"] = a.similarity
    global RUNS_GLOB
    RUNS_GLOB = a.runs
    rows = await from_firestore("(default)") + await from_firestore("dev-db") + await from_accept_runs()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    sim = get_config().source_tiers["evidence_score"]["same_origin_similarity"]
    path = ROOT / "runs" / f"replay-evidence-score-{stamp}-sim{sim}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"same_origin_similarity {sim}, runs {RUNS_GLOB}\n")
    print(report(rows))
    print(f"\nrows: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
