"""Tool calls made by the fan-out agents: Fact Check Tools API, Cloud Vision web detection, the
`sources` offender list, RDAP domain age, and page publish dates.

Agents never call HTTP directly; they take a Tools object. `make record` wraps it in RecordingTools
and saves results next to the model fixtures; `make test` replays them with ReplayTools, so the whole
pipeline runs offline on real recorded data.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.settings import get_settings
from app.store import Store

log = logging.getLogger(__name__)
FACTCHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
SOURCES = "sources"


def source_key(domain_or_handle: str) -> str:
    """Doc id in `sources`: lowercase domain without www, or @handle."""
    k = domain_or_handle.strip().lower()
    if k.startswith("@"):
        return k
    return k.removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]


class Tools:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def factcheck_search(self, query: str, language_code: str) -> list[dict[str, Any]]:
        """Published fact checks (ClaimReview) matching the query. Empty list on any failure.
        language_code "" searches fact checks in every language."""
        key = get_settings().factcheck_api_key
        if not key or not query.strip():
            return []
        params = {"query": query[:300], "pageSize": 8, "key": key}
        if language_code:
            params["languageCode"] = language_code
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(FACTCHECK_URL, params=params)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("factcheck search failed: %s", type(e).__name__)
            return []
        out = []
        for claim in r.json().get("claims", []):
            for rev in claim.get("claimReview", [])[:2]:
                out.append({
                    "claim_text": claim.get("text"), "claimant": claim.get("claimant"),
                    "claim_date": claim.get("claimDate"), "url": rev.get("url"),
                    "publisher": (rev.get("publisher") or {}).get("name"),
                    "publisher_site": (rev.get("publisher") or {}).get("site"),
                    "rating": rev.get("textualRating"), "review_date": rev.get("reviewDate"),
                    "title": rev.get("title"), "language": rev.get("languageCode"),
                })
        return out

    async def vision_web_detection(self, image_uri: str | None = None, content: bytes | None = None
                                   ) -> dict[str, Any]:
        """Cloud Vision WEB_DETECTION for a gs:// image, a local path (dev) or raw bytes."""
        if image_uri and image_uri.startswith("gs://"):
            image: dict[str, Any] = {"source": {"gcsImageUri": image_uri}}
        else:
            data = content if content is not None else await asyncio.to_thread(Path(image_uri or "").read_bytes)
            image = {"content": base64.b64encode(data).decode()}
        body = {"requests": [{"image": image, "features": [{"type": "WEB_DETECTION", "maxResults": 15}]}]}
        try:
            token, is_user = await asyncio.to_thread(_access_token)
            headers = {"Authorization": f"Bearer {token}"}
            if is_user:
                # Local dev with user credentials needs a quota project; Cloud Run's service account
                # does not (and would need serviceusage.consumer to send this header).
                headers["x-goog-user-project"] = get_settings().gcp_project
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(VISION_URL, json=body, headers=headers)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001  provenance is one lane; never fail the check
            log.warning("vision web detection failed: %s", e)
            return {}
        wd = (r.json().get("responses") or [{}])[0].get("webDetection") or {}
        return {
            "best_guess": [b.get("label") for b in wd.get("bestGuessLabels", [])],
            "entities": [e.get("description") for e in wd.get("webEntities", [])[:8] if e.get("description")],
            "pages": [{
                "url": p.get("url"), "title": p.get("pageTitle"),
                "full_matches": len(p.get("fullMatchingImages", [])),
                "partial_matches": len(p.get("partialMatchingImages", [])),
            } for p in wd.get("pagesWithMatchingImages", [])[:12] if p.get("url")],
        }

    async def lookup_source(self, domain_or_handle: str) -> dict[str, Any] | None:
        """Offender record from `sources` (seeded from published fact checks), or None."""
        return await self.store.get(SOURCES, source_key(domain_or_handle))

    async def domain_info(self, domain: str) -> dict[str, Any]:
        """Registration date and age in days from RDAP. Empty dict when unknown."""
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as c:
                r = await c.get(f"https://rdap.org/domain/{source_key(domain)}")
            r.raise_for_status()
            events = r.json().get("events", [])
        except (httpx.HTTPError, ValueError):
            return {}
        reg = next((e.get("eventDate") for e in events if e.get("eventAction") == "registration"), None)
        if not reg:
            return {}
        when = datetime.fromisoformat(reg.replace("Z", "+00:00"))
        return {"registered": when.date().isoformat(), "age_days": (datetime.now(UTC) - when).days}

    async def page_date(self, url: str) -> str | None:
        """Publish date of a web page from its meta tags (media provenance: earliest appearance)."""
        from app.intake import links

        f = links.Fetcher()
        try:
            async with asyncio.timeout(4):
                _, _, body = await f.get(url, accept="text/html")
            meta, _ = links.parse_meta(body[:400_000].decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return None
        finally:
            await f.aclose()
        for k in ("article:published_time", "og:published_time", "datepublished", "date", "pubdate"):
            if meta.get(k):
                return meta[k][:10]
        return None


_creds = None


def _access_token() -> tuple[str, bool]:
    """(token, is_user_credentials)."""
    global _creds
    import google.auth
    import google.auth.transport.requests

    if _creds is None:
        _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _creds.valid:
        _creds.refresh(google.auth.transport.requests.Request())
    return _creds.token, getattr(_creds, "service_account_email", None) is None


# ---------- record / replay (make record, make test) ----------

def _call_key(name: str, args: tuple, kwargs: dict) -> str:
    def norm(v: Any) -> Any:
        if isinstance(v, bytes):
            return "sha256:" + hashlib.sha256(v).hexdigest()
        if isinstance(v, str) and (v.startswith("/") or v.startswith("gs://")):
            return "path:" + Path(v).name  # media paths differ per run; the file name is stable
        return v

    return f"{name}:" + json.dumps([norm(a) for a in args] + [[k, norm(v)] for k, v in sorted(kwargs.items())],
                                   ensure_ascii=False)


class RecordingTools(Tools):
    def __init__(self, inner: Tools) -> None:
        super().__init__(inner.store)
        self.inner = inner
        self.calls: dict[str, Any] = {}

    def __getattribute__(self, name: str):
        if name in ("factcheck_search", "vision_web_detection", "lookup_source", "domain_info", "page_date"):
            fn = getattr(object.__getattribute__(self, "inner"), name)

            async def wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                object.__getattribute__(self, "calls")[_call_key(name, args, kwargs)] = result
                return result

            return wrapper
        return object.__getattribute__(self, name)


class ReplayTools(Tools):
    """Returns recorded results; an unrecorded call gets the tool's empty result (never the network)."""

    EMPTY = {"factcheck_search": [], "vision_web_detection": {}, "lookup_source": None, "domain_info": {},
             "page_date": None}

    def __init__(self, store: Store, calls: dict[str, Any]) -> None:
        super().__init__(store)
        self.recorded = calls

    def __getattribute__(self, name: str):
        empty = object.__getattribute__(self, "EMPTY")
        if name in empty:
            recorded = object.__getattribute__(self, "recorded")

            async def replay(*args, **kwargs):
                return recorded.get(_call_key(name, args, kwargs), empty[name])

            return replay
        return object.__getattribute__(self, name)


def default_tools(store: Store) -> Tools:
    """Real tools, except in LLM_MODE=fake (tests, offline UI work): nothing leaves the machine."""
    if get_settings().llm_mode == "fake":
        return ReplayTools(store, {})
    return Tools(store)
