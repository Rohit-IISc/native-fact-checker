"""Seed the production cache with the demo shares (docs/14: "the first thing a judge tries is instant").

Every seeded verdict comes from a real pipeline run against production (uid "demo-seed"), never written by
hand. For each acceptance case (tests/acceptance/*.yaml; re-share cases with `after:` are skipped, they test
that the first share's verdict is reused):
  1. Look up the production cache exactly as POST /v1/checks does.
  2. If it already answers with an expected label, keep it.
  3. Otherwise run the pipeline (up to --tries times). A run whose label is not expected is deleted with
     everything it wrote (verdicts, tier 2 claim index, audio), so a wrong answer never stays cached; cache
     entries pointing to deleted verdicts stop answering, and the next run overwrites them.

Every demo verdict the cache answers with is pinned (pinned: true, no expires_at), so it never expires during
judging, NOT_ENOUGH_EVIDENCE ones included. Media cases read their file from the repo or, when it is not on the
machine (samples/ is never committed), from gs://{project}-eval/demo-media/ (private), so the daily Cloud Run job
(`--check`, scripts/deploy_demo_check.sh) can re-seed anything missing.

Usage (from backend/):
  STORE=firestore FIRESTORE_DB="(default)" PYTHONPATH=.:.. uv run python ../scripts/seed_demo_cache.py         # report
  STORE=firestore FIRESTORE_DB="(default)" PYTHONPATH=.:.. uv run python ../scripts/seed_demo_cache.py --seed  # seed
  ... seed_demo_cache.py --check   # seed what is missing (2 tries), pin, exit 1 if a case could not be seeded
Costs about 0.10-0.15 USD per pipeline run.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = "https://chckr.web.app"

# Seeded verdicts store absolute audio links, so they must be built with the production address. In a
# Codespace the settings prefer the forwarded dev URL (Oct 16: 15 seeded audio links pointed at it).
os.environ.pop("CODESPACE_NAME", None)
os.environ["PUBLIC_BASE_URL"] = PUBLIC

from app.agents.tools import default_tools  # noqa: E402
from app.devtools import harness  # noqa: E402
from app.devtools.accept import load_cases  # noqa: E402
from app.llm import get_llm  # noqa: E402
from app.pipeline.results import VERDICTS  # noqa: E402
from app.settings import get_settings  # noqa: E402
from app.store import get_store  # noqa: E402

UID = "demo-seed"


def labels_of(hit: dict | None) -> list[str]:
    if not hit:
        return []
    if hit.get("non_checkable"):
        return ["NOT_CHECKABLE"]
    return [v["label"] for v in hit["verdicts"]]


def passes(labels: list[str], expected: list[str]) -> bool:
    return bool(labels) and labels[0] in expected


async def delete_run(store, check_id: str) -> None:
    """Everything a failed attempt wrote: its verdicts, their tier 2 index entries and audio, its check."""
    from google.cloud import firestore, storage
    from google.cloud.firestore_v1.base_query import FieldFilter

    s = get_settings()
    db = firestore.Client(project=s.gcp_project, database=s.firestore_db)
    outputs = storage.Client(project=s.gcp_project).bucket(s.outputs_bucket)
    for v in db.collection(VERDICTS).where(filter=FieldFilter("check_id", "==", check_id)).stream():
        for cd in db.collection("claims").where(filter=FieldFilter("verdict_id", "==", v.id)).stream():
            cd.reference.delete()
        for blob in outputs.list_blobs(prefix=f"audio/{v.id}_"):
            blob.delete()
        v.reference.delete()
    db.collection("checks").document(check_id).delete()


def media_file(rel: str) -> Path | None:
    """The demo media file: in the repo checkout, else downloaded from the private eval bucket."""
    local = ROOT / rel
    if local.exists():
        return local
    from google.cloud import storage

    s = get_settings()
    blob = storage.Client(project=s.gcp_project).bucket(s.eval_bucket).blob(f"demo-media/{rel}")
    if not blob.exists():
        return None
    dest = Path("/tmp/demo-media") / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(dest))
    return dest


async def pin(store, hit: dict | None) -> list[str]:
    """Pinned verdicts never expire (tier1._usable ignores expires_at for them)."""
    ids = [v["verdict_id"] for v in (hit or {}).get("verdicts") or []]
    for vid in ids:
        await store.set(VERDICTS, vid, {"pinned": True, "expires_at": None}, merge=True)
    return ids


async def main(seed: bool, tries: int, only: str | None) -> int:
    s = get_settings()
    if s.store != "firestore" or s.firestore_db != "(default)":
        raise SystemExit('Run with STORE=firestore FIRESTORE_DB="(default)": the demo cache is production')
    if s.public_base_url != PUBLIC:
        raise SystemExit(f"public base URL is {s.public_base_url}, not {PUBLIC}: links stored now would be wrong")
    store, llm = get_store(), get_llm()
    rows = []
    for case in load_cases():
        if case.after or (only and only not in case.id):
            continue
        file = case.input.get("file")
        path = media_file(file) if file else None
        if file and not path:
            rows.append((case.id, "skipped: media not found", ""))
            continue
        req, keys, _ = await harness.build_request(case.input.get("text"), path and str(path), case.input.get("url"))
        req = req.model_copy(update={"uid": UID})
        hit = await harness._tier1_lookup(store, req, keys)
        cached = labels_of(hit)
        if passes(cached, case.expected):
            await pin(store, hit)
            rows.append((case.id, "already cached, pinned", "/".join(cached)))
            continue
        if not seed:
            rows.append((case.id, f"needs seeding (cache: {'/'.join(cached) or 'none'})", ""))
            continue
        status, got = "FAILED to seed", ""
        for attempt in range(1, tries + 1):
            if attempt > 1:  # a fresh check id for each attempt
                req, keys, _ = await harness.build_request(case.input.get("text"), path and str(path),
                                                           case.input.get("url"))
                req = req.model_copy(update={"uid": UID})
            run, _ = await harness.run(req, store=store, llm=llm, cache_keys=keys, tools=default_tools(store))
            got = run.label
            print(f"  {case.id} attempt {attempt}: {got}", flush=True)
            if passes([run.primary_label], case.expected) and run.result and not run.result.degraded:
                status = f"seeded (attempt {attempt}), pinned"
                await pin(store, await harness._tier1_lookup(store, req, keys))
                break
            await delete_run(store, req.check_id)
        rows.append((case.id, status, got))
    print(f"\n{'case':34} {'status':44} verdict")
    for r in rows:
        print(f"{r[0]:34} {r[1]:44} {r[2]}")
    failed = [r[0] for r in rows if r[1].startswith(("FAILED", "skipped"))]
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="run the pipeline for cases the cache does not answer")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--case", help="only cases whose id contains this")
    ap.add_argument("--check", action="store_true", help="daily job: seed only what is missing (2 tries)")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.seed or a.check, 2 if a.check else a.tries, a.case)))
