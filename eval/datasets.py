"""Eval datasets (docs/10): built from published fact checks (Fact Check Tools API, ClaimReview).

FactDRIL is not used: its release is tweet IDs and links, not ready claims. Instead we harvest ClaimReview
items in the five demo languages, which gives the same structure (claim text, language, fact check URL,
rating). The text belongs to the fact-checkers, so datasets live in gs://{project}-eval/datasets/{version}/
and never in this public repo (eval/datasets/ is gitignored; a local copy is cached there).

- benchmark.jsonl: claims for cross-lingual recall at 5 (balanced across languages)
- gold.jsonl: claims whose rating maps clearly onto our labels, for verdict regression

A dataset version is frozen once built: the baseline and every later run must use the same items.
Build one:  cd backend && uv run python -m eval.datasets build --version v1
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "eval" / "datasets"
LANGUAGES = ["hi", "ta", "kn", "id", "en"]
TOPICS = ["election", "flood", "riot", "army", "vaccine", "cure", "cancer", "scheme", "free", "loan", "job",
          "minister", "temple", "police", "bank", "petrol", "school", "earthquake", "video", "photo"]
# Same topics in each language, so non-English queries match non-English fact checks.
TOPICS_NATIVE = {
    "hi": ["चुनाव", "बाढ़", "सेना", "वैक्सीन", "इलाज", "योजना", "मुफ्त", "मंत्री", "पुलिस", "वीडियो", "फोटो"],
    "ta": ["தேர்தல்", "வெள்ளம்", "தடுப்பூசி", "திட்டம்", "இலவச", "அமைச்சர்", "காவல்", "வீடியோ", "புகைப்படம்"],
    "kn": ["ಚುನಾವಣೆ", "ಪ್ರವಾಹ", "ಲಸಿಕೆ", "ಯೋಜನೆ", "ಉಚಿತ", "ಸಚಿವ", "ಪೊಲೀಸ್", "ವಿಡಿಯೋ", "ಫೋಟೋ"],
    "id": ["pemilu", "banjir", "vaksin", "obat", "bantuan", "gratis", "menteri", "polisi", "video", "foto"],
}

# Rating text to our label: lowercase substring rules, checked in this order. Anything else is left out
# of the gold set (ratings like "partly true" or "unproven" do not map cleanly onto one label).
RATING_RULES: list[tuple[str, list[str]]] = [
    ("SCAM", ["scam", "fraud", "phishing", "penipuan", "धोखाधड़ी", "மோசடி", "ವಂಚನೆ"]),
    ("MISLEADING", ["misleading", "mislead", "out of context", "missing context", "altered", "edited", "satire",
                    "old video", "old photo", "old image", "partly false", "half true", "menyesatkan", "sesat",
                    "भ्रामक", "தவறாக வழிநடத்தும்", "ದಾರಿತಪ್ಪಿಸುವ"]),
    ("FALSE", ["false", "fake", "fabricated", "hoax", "baseless", "incorrect", "wrong", "not true", "untrue", "salah",
               "palsu", "hoaks", "झूठ", "फर्जी", "फेक", "गलत", "தவறு", "போலி", "பொய்", "ತಪ್ಪು", "ಸುಳ್ಳು", "ನಕಲಿ"]),
    ("TRUE", ["true", "correct", "accurate", "benar", "सच", "सही", "உண்மை", "ನಿಜ"]),
]
_UNCLEAR = re.compile(r"partly|mostly|half|unproven|unverified|mixed|explainer|no evidence|research in progress"
                      r"|sebagian|sebagian besar|kurang tepat",
                      re.IGNORECASE)


def label_for_rating(rating: str | None) -> str | None:
    """Our label for a fact-checker's textual rating, or None when it does not map cleanly."""
    r = (rating or "").strip().lower()
    if not r:
        return None
    for label, words in RATING_RULES:
        if any(w in r for w in words):
            if label in ("TRUE", "FALSE") and _UNCLEAR.search(r):
                return None
            return label
    return None


def item_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def norm_url(url: str | None) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://(www\.|m\.|amp\.)?", "", u)
    return u.split("?")[0].split("#")[0].rstrip("/").removesuffix("/amp")


async def harvest(per_query: int = 50) -> list[dict]:
    """All ClaimReview items found for the topic queries in the demo languages, one per fact-check URL."""
    import httpx

    from app.agents.tools import FACTCHECK_URL
    from app.settings import get_settings

    key = get_settings().factcheck_api_key
    if not key:
        raise SystemExit("FACTCHECK_API_KEY is not set")
    queries = [(t, lang) for lang in LANGUAGES for t in TOPICS + TOPICS_NATIVE.get(lang, [])]
    items: dict[str, dict] = {}
    sem = asyncio.Semaphore(4)

    async def one(c: httpx.AsyncClient, q: str, lang: str) -> None:
        async with sem:
            try:
                r = await c.get(FACTCHECK_URL, params={"query": q, "languageCode": lang, "pageSize": per_query,
                                                       "key": key})
                r.raise_for_status()
            except httpx.HTTPError:
                return
        for claim in r.json().get("claims", []):
            for rev in claim.get("claimReview", [])[:1]:
                url, text = rev.get("url"), (claim.get("text") or "").strip()
                if not url or len(text) < 25 or rev.get("languageCode", lang) != lang:
                    continue
                items.setdefault(norm_url(url), {
                    "id": item_id(url), "claim_text": text[:600], "language": lang, "url": url,
                    "publisher": (rev.get("publisher") or {}).get("name"), "rating": rev.get("textualRating"),
                    "label": label_for_rating(rev.get("textualRating")), "review_date": rev.get("reviewDate"),
                })

    async with httpx.AsyncClient(timeout=15.0) as c:
        await asyncio.gather(*(one(c, q, lang) for q, lang in queries))
    return list(items.values())


def balanced(items: list[dict], per_language: int, rng: random.Random, by_label: bool = False) -> list[dict]:
    """Up to per_language items for each demo language; with by_label, spread across labels first."""
    out = []
    for lang in LANGUAGES:
        pool = [i for i in items if i["language"] == lang]
        rng.shuffle(pool)
        if by_label:
            groups = {lab: [i for i in pool if i["label"] == lab] for lab in ("TRUE", "SCAM", "MISLEADING", "FALSE")}
            pick: list[dict] = []
            while len(pick) < per_language and any(groups.values()):
                for lab in groups:
                    if groups[lab] and len(pick) < per_language:
                        pick.append(groups[lab].pop())
            out += pick
        else:
            out += pool[:per_language]
    return out


# ---------- storage (GCS, cached locally) ----------

def _bucket() -> str:
    from app.settings import get_settings

    return f"{get_settings().gcp_project}-eval"


def save(version: str, name: str, rows: list[dict]) -> str:
    from google.cloud import storage

    data = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    (LOCAL / version).mkdir(parents=True, exist_ok=True)
    (LOCAL / version / name).write_text(data, encoding="utf-8")
    blob = storage.Client().bucket(_bucket()).blob(f"datasets/{version}/{name}")
    if blob.exists():
        raise SystemExit(f"gs://{_bucket()}/datasets/{version}/{name} exists: versions are frozen, pick a new one")
    blob.upload_from_string(data, content_type="application/jsonl")
    return f"gs://{_bucket()}/datasets/{version}/{name}"


def load(version: str, name: str) -> list[dict]:
    path = LOCAL / version / name
    if not path.exists():
        from google.cloud import storage

        path.parent.mkdir(parents=True, exist_ok=True)
        storage.Client().bucket(_bucket()).blob(f"datasets/{version}/{name}").download_to_filename(str(path))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_version() -> str:
    from google.cloud import storage

    names = {b.name.split("/")[1] for b in storage.Client().list_blobs(_bucket(), prefix="datasets/")
             if b.name.count("/") >= 2}
    if not names:
        raise SystemExit("no eval dataset yet: run `python -m eval.datasets build --version v1`")
    return sorted(names, key=lambda v: int(re.sub(r"\D", "", v) or 0))[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="harvest ClaimReview items and freeze a dataset version")
    b.add_argument("--version", required=True)
    b.add_argument("--benchmark-per-language", type=int, default=40)  # 200 claims for recall at 5
    b.add_argument("--gold-per-language", type=int, default=12)       # 60 claims for verdict regression
    b.add_argument("--seed", type=int, default=20261009)
    a = ap.parse_args()
    items = asyncio.run(harvest())
    rng = random.Random(a.seed)
    bench = balanced(items, a.benchmark_per_language, rng)
    gold_ids = {i["id"] for i in bench}
    gold = balanced([i for i in items if i["label"] and i["id"] not in gold_ids], a.gold_per_language, rng,
                    by_label=True)
    print(f"harvested {len(items)} fact checks; benchmark {len(bench)}, gold {len(gold)}")
    for lang in LANGUAGES:
        labels = [g["label"] for g in gold if g["language"] == lang]
        print(f"  {lang}: benchmark {sum(i['language'] == lang for i in bench)}, gold {len(labels)} "
              f"{ {lab: labels.count(lab) for lab in sorted(set(labels))} }")
    print(save(a.version, "benchmark.jsonl", bench))
    print(save(a.version, "gold.jsonl", gold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
