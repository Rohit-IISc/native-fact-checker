"""Seed the `sources` offender list from published fact checks (docs/09, "Building the offender list").

No hand-picked lists and no partisan labels: a domain or @handle gets a record only because
fact-checkers rated content it published false or misleading. A source is a repeat offender at 3+.

Usage (from backend/):  uv run python ../scripts/seed_sources.py [--db dev-db|"(default)"] [--dry-run]
Reads FACTCHECK_API_KEY and GCP_PROJECT like the backend (env > backend/.env > backend/.env.defaults).
Re-running recomputes counts from scratch (idempotent). Rows from our own verdicts (origin OWN_VERDICTS)
are kept separate and are not touched here.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.agents.tools import FACTCHECK_URL, SOURCES, source_key  # noqa: E402
from app.settings import get_settings  # noqa: E402

TOPICS = ["election", "vote", "flood", "riot", "war", "army", "vaccine", "covid", "cure", "cancer", "scheme",
          "free", "loan", "lottery", "job", "celebrity", "minister", "temple", "mosque", "police", "bank",
          "rupee", "petrol", "school", "earthquake"]
LANGUAGES = ["en", "hi", "ta", "kn", "te", "ml", "mr", "bn", "id"]
PAGES = 3
PAGE_SIZE = 100
REPEAT_OFFENDER_AT = 3

# Ratings that count against the claimant, in the words publishers use (lowercased substring match).
NEGATIVE = ["false", "fake", "misleading", "mislead", "out of context", "altered", "manipulated", "scam",
            "fabricated", "satire presented as fact", "incorrect", "wrong", "hoax", "baseless", "edited",
            "झूठ", "फर्जी", "भ्रामक", "गलत", "फेक", "தவறு", "போலி", "ತಪ್ಪು", "ಸುಳ್ಳು", "తప్పు", "തെറ്റ്",
            "खोटे", "মিথ্যা", "salah", "keliru", "hoaks", "menyesatkan", "palsu", "disinformasi"]
NOT_NEGATIVE = ["not false", "mostly true", "true", "correct", "सच", "benar"]
_DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/.*)?$", re.I)
_HANDLE = re.compile(r"^@[A-Za-z0-9_.]{2,30}$")
_SOCIAL_HOSTS = {"facebook.com", "x.com", "twitter.com", "instagram.com", "youtube.com", "t.me", "whatsapp.com"}


def is_negative(rating: str | None) -> bool:
    r = (rating or "").strip().lower()
    if not r or any(p == r or r.startswith(p + " ") for p in NOT_NEGATIVE):
        return False
    return any(n in r for n in NEGATIVE)


def claimant_key(claimant: str | None) -> str | None:
    """A domain or @handle we can look up later; free-text names ("Social media users") are skipped."""
    c = (claimant or "").strip()
    if _HANDLE.match(c):
        return c.lower()
    m = _DOMAIN.match(c)
    if m and m.group(1).lower() not in _SOCIAL_HOSTS:
        return source_key(m.group(1))
    return None


def _host(value: str | None) -> str:
    m = _DOMAIN.match((value or "").strip())
    return source_key(m.group(1)) if m else ""


def is_self_review(claimant: str, review: dict, review_url: str) -> bool:
    """True when the claimant is the fact-checker that wrote the review (same site or a subdomain)."""
    if claimant.startswith("@"):
        return False
    publisher = {_host((review.get("publisher") or {}).get("site")), _host(review_url)} - {""}
    return any(claimant == p or claimant.endswith("." + p) or p.endswith("." + claimant) for p in publisher)


async def harvest(key: str) -> dict[str, dict]:
    seen_reviews: set[str] = set()
    skipped_self: dict[str, int] = defaultdict(int)
    records: dict[str, dict] = defaultdict(lambda: {"count": 0, "examples": []})
    sem = asyncio.Semaphore(3)  # the API rate-limits bursts (429s at 8 concurrent)

    async def one(client: httpx.AsyncClient, query: str, lang: str) -> None:
        token = None
        for _ in range(PAGES):
            params = {"query": query, "languageCode": lang, "pageSize": PAGE_SIZE, "key": key}
            if token:
                params["pageToken"] = token
            async with sem:
                r = None
                for attempt in range(4):  # the API rate-limits bursts: back off on 429 and 5xx
                    try:
                        r = await client.get(FACTCHECK_URL, params=params)
                    except httpx.HTTPError:
                        r = None
                    if r is not None and r.status_code < 400:
                        break
                    await asyncio.sleep(2 ** attempt)
                if r is None or r.status_code >= 400:
                    print(f"  {lang}/{query}: gave up ({r.status_code if r is not None else 'network'})",
                          file=sys.stderr)
                    return
            data = r.json()
            for claim in data.get("claims", []):
                k = claimant_key(claim.get("claimant"))
                for rev in claim.get("claimReview", []):
                    url = rev.get("url")
                    if not k or not url or url in seen_reviews or not is_negative(rev.get("textualRating")):
                        continue
                    if is_self_review(k, rev, url):
                        # Some publishers (seen: tempo.co, suara.com, tirto.id) put their own site in the
                        # claimant field. Counting that would brand the fact-checker an offender.
                        skipped_self[k] += 1
                        continue
                    seen_reviews.add(url)
                    rec = records[k]
                    rec["count"] += 1
                    rec["examples"].append({
                        "claim": (claim.get("text") or "")[:200], "rating": rev.get("textualRating"),
                        "publisher": (rev.get("publisher") or {}).get("name"), "url": url,
                        "date": (rev.get("reviewDate") or "")[:10]})
            token = data.get("nextPageToken")
            if not token:
                return

    async with httpx.AsyncClient(timeout=20.0) as client:
        await asyncio.gather(*(one(client, q, lang) for q in TOPICS for lang in LANGUAGES))
    print(f"scanned {len(seen_reviews)} negative reviews with a domain or handle claimant")
    if skipped_self:
        top = sorted(skipped_self.items(), key=lambda kv: -kv[1])[:8]
        print(f"skipped claimant == reviewing publisher: {', '.join(f'{k} ({n})' for k, n in top)}")
    return records


async def write(db_name: str, records: dict[str, dict], dry_run: bool) -> None:
    now = datetime.now(UTC).isoformat()
    rows = {}
    for k, rec in records.items():
        examples = sorted(rec["examples"], key=lambda e: e["date"], reverse=True)[:3]
        rows[k] = {"key": k, "repeat_offender_count": rec["count"],
                   "repeat_offender": rec["count"] >= REPEAT_OFFENDER_AT, "examples": examples,
                   "origin": "FACT_CHECK_HARVEST", "updated_at": now}
    top = sorted(rows.values(), key=lambda r: -r["repeat_offender_count"])[:15]
    for r in top:
        print(f"  {r['repeat_offender_count']:>3}  {r['key']}")
    offenders = sum(r["repeat_offender"] for r in rows.values())
    print(f"{len(rows)} sources, {offenders} repeat offenders (>= {REPEAT_OFFENDER_AT})")
    if dry_run:
        return
    from google.cloud import firestore

    db = firestore.AsyncClient(project=get_settings().gcp_project, database=db_name)
    batch, n = db.batch(), 0
    for k, row in rows.items():
        batch.set(db.collection(SOURCES).document(k), row, merge=True)
        n += 1
        if n % 400 == 0:
            await batch.commit()
            batch = db.batch()
    await batch.commit()
    print(f"wrote {n} docs to {db_name}/{SOURCES}")


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=None, help="Firestore database (default: FIRESTORE_DB from settings)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    s = get_settings()
    if not s.factcheck_api_key:
        sys.exit("FACTCHECK_API_KEY is not set")
    records = await harvest(s.factcheck_api_key)
    await write(a.db or s.firestore_db, records, a.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
