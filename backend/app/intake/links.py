"""Link fetch ladder (docs/03 stage 1): turn a shared URL into text and media for the extractor.

Order: expand redirects -> YouTube -> X oEmbed -> Meta oEmbed -> generic page (Open Graph +
trafilatura + og:image). Every hop passes the SSRF guard; 10 s total, 5 MB max body. Returns a
FetchedPost; fetch_method="failed" when nothing usable came back.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

import httpx

from app.intake.ssrf import BlockedURL, resolve_public
from app.intake.validate import sniff
from app.models import FetchedPost
from app.settings import get_config

log = logging.getLogger(__name__)
MAX_BODY = 5 * 1024 * 1024
MAX_REDIRECTS = 5
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Mobile Safari/537.36"
# What a post with a photo or video looks like in its text when the platform does not give us the media.
_MEDIA_HINT = re.compile(r"pic\.twitter\.com|pic\.x\.com|/photo/|/video/|https://t\.co/", re.I)


SHORTENERS = {"t.co", "bit.ly", "tinyurl.com", "fb.watch", "goo.gl", "ow.ly", "buff.ly", "rb.gy", "shorturl.at",
              "cutt.ly", "is.gd", "dlvr.it", "amzn.to", "wa.me"}


class FetchFailed(Exception):
    pass


def platform_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host in ("youtube.com", "youtu.be", "music.youtube.com") or host.endswith(".youtube.com"):
        return "youtube"
    if host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com", "vxtwitter.com"):
        return "x"
    if host.endswith("instagram.com"):
        return "instagram"
    if host.endswith("facebook.com") or host == "fb.watch":
        return "facebook"
    if host.endswith("linkedin.com"):
        return "linkedin"
    if host in ("t.me", "telegram.me"):
        return "telegram"
    return "other"


class Fetcher:
    """HTTP with the SSRF guard at every hop. `transport` and `resolver` are injectable for tests."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, resolver=None) -> None:
        self._client = httpx.AsyncClient(transport=transport, follow_redirects=False,
                                         headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.8"},
                                         timeout=httpx.Timeout(8.0))
        self._resolver = resolver

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, *, accept: str = "*/*") -> tuple[str, httpx.Response, bytes]:
        """GET following up to 5 redirects. Returns (final_url, response, body capped at 5 MB)."""
        for _ in range(MAX_REDIRECTS + 1):
            await resolve_public(url, self._resolver)
            async with self._client.stream("GET", url, headers={"Accept": accept}) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise FetchFailed(f"HTTP {resp.status_code} for {url}")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BODY:
                        raise FetchFailed("body over 5 MB")
                return url, resp, bytes(body)
        raise FetchFailed("too many redirects")

    async def json(self, url: str) -> dict:
        _, _, body = await self.get(url, accept="application/json")
        import json

        return json.loads(body)


# ---------- HTML parsing ----------

class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_meta(page: str) -> tuple[dict[str, str], str]:
    p = _Meta()
    try:
        p.feed(page)
    except Exception:  # noqa: BLE001  malformed HTML: keep what we parsed
        pass
    return p.meta, p.title.strip()


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html.unescape(text)).strip()


# ---------- ladder steps ----------

async def _youtube(f: Fetcher, url: str) -> FetchedPost:
    title = author = None
    try:
        data = await f.json(f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}")
        title, author = data.get("title"), data.get("author_name")
    except Exception as e:  # noqa: BLE001  Gemini reads the video itself; the title is a bonus
        log.info("youtube oembed failed: %s", e)
    return FetchedPost(source_url=url, platform="youtube", title=title, text=title, author_handle=author,
                       youtube_url=url, fetch_method="youtube")


async def _x(f: Fetcher, url: str) -> FetchedPost | None:
    canonical = re.sub(r"^https?://(www\.|mobile\.)?(x|twitter|fxtwitter|vxtwitter)\.com", "https://twitter.com", url)
    try:
        data = await f.json(
            f"https://publish.twitter.com/oembed?omit_script=1&dnt=true&url={quote(canonical, safe='')}")
    except Exception as e:  # noqa: BLE001
        log.info("x oembed failed: %s", e)
        return None
    block = data.get("html") or ""
    m = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
    text = _strip_tags(m.group(1)) if m else None
    handle = (data.get("author_url") or "").rstrip("/").rsplit("/", 1)[-1] or None
    dm = re.search(r"&mdash;.*?<a[^>]*>([A-Za-z]+ \d{1,2}, \d{4})</a>", block, re.S)
    published = datetime.strptime(dm.group(1), "%B %d, %Y") if dm else None
    return FetchedPost(source_url=url, platform="x", text=text, author_handle=handle and f"@{handle}",
                       published_at=published, media_missing=bool(_MEDIA_HINT.search(block)),
                       fetch_method="x_oembed")


async def _meta(f: Fetcher, url: str, platform: str) -> FetchedPost | None:
    token = os.environ.get("META_OEMBED_TOKEN")
    if not token:
        return None
    kind = "instagram_oembed" if platform == "instagram" else "oembed_post"
    try:
        data = await f.json(f"https://graph.facebook.com/v21.0/{kind}?url={quote(url, safe='')}&access_token={token}")
    except Exception as e:  # noqa: BLE001
        log.info("meta oembed failed: %s", e)
        return None
    text = _strip_tags(data.get("html") or "") or data.get("title")
    if not text:
        return None
    return FetchedPost(source_url=url, platform=platform, text=text, media_missing=True,  # type: ignore[arg-type]
                       fetch_method="meta_oembed")


async def _page(f: Fetcher, url: str, platform: str, store_image) -> FetchedPost | None:
    final_url, resp, body = await f.get(url, accept="text/html,application/xhtml+xml")
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and not body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        raise FetchFailed(f"not HTML: {ctype}")
    page = body.decode(resp.encoding or "utf-8", errors="replace")
    meta, title = parse_meta(page)
    import trafilatura

    main = await asyncio.to_thread(trafilatura.extract, page, url=final_url, include_comments=False,
                                   include_tables=False, favor_precision=True)
    og_title = meta.get("og:title") or meta.get("twitter:title") or title or None
    desc = meta.get("og:description") or meta.get("twitter:description") or meta.get("description")
    text = main or desc
    if not (text or og_title):
        return None
    image_uris = []
    if (img := meta.get("og:image") or meta.get("twitter:image")) and store_image:
        try:
            _, _, data = await f.get(urljoin(final_url, img), accept="image/*")
            if sniff(data) and sniff(data)[0] == "image":
                image_uris.append(await store_image(data, sniff(data)[1]))
        except Exception as e:  # noqa: BLE001  the page text alone is still useful
            log.info("og:image fetch failed: %s", e)
    is_social = platform in ("instagram", "facebook", "x")
    return FetchedPost(
        source_url=url, platform=platform if platform != "other" else "news",  # type: ignore[arg-type]
        title=og_title, text=(f"{desc}\n\n{main}" if desc and main and desc not in main else text),
        published_at=_date(meta.get("article:published_time") or meta.get("og:published_time")),
        author_handle=meta.get("author") or meta.get("article:author"),
        image_uris=image_uris, media_missing=is_social, fetch_method="open_graph" if not main else "html",
    )


async def fetch(url: str, *, store_image=None, transport=None, resolver=None) -> FetchedPost:
    """Run the ladder within the link_fetch deadline. Never raises: failure is fetch_method="failed"."""
    f = Fetcher(transport, resolver)
    platform = platform_of(url)
    try:
        async with asyncio.timeout(get_config().timeout("link_fetch")):
            # Short links first: the platform is that of the target (bit.ly to an X post is an X post).
            if (urlsplit(url).hostname or "").removeprefix("www.") in SHORTENERS:
                try:
                    final, _, _ = await f.get(url, accept="text/html")
                    if platform_of(final) != "other":
                        url, platform = final, platform_of(final)
                except (FetchFailed, httpx.HTTPError):
                    pass
            post = None
            if platform == "youtube":
                post = await _youtube(f, url)
            elif platform == "x":
                post = await _x(f, url)
            elif platform in ("instagram", "facebook"):
                post = await _meta(f, url, platform)
            if post is None:
                post = await _page(f, url, platform, store_image)
            if post is not None:
                return post
    except BlockedURL as e:
        log.warning("link blocked: %s", e)
    except (TimeoutError, FetchFailed, httpx.HTTPError, ValueError) as e:
        log.info("link fetch failed: %r", e)
    finally:
        await f.aclose()
    return FetchedPost(source_url=url, platform=platform, media_missing=True, fetch_method="failed")  # type: ignore[arg-type]
