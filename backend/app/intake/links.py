"""Link fetch ladder (docs/03 stage 1): turn a shared URL into text and media for the extractor.

Order: expand redirects -> YouTube -> X oEmbed -> Meta oEmbed (tokenless) -> page (Open Graph +
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
# An honest link-preview bot UA. Instagram and Facebook serve Open Graph tags (caption, author,
# date, photo) to link-preview bots and a login wall to browser UAs.
UA = "Mozilla/5.0 (compatible; FactCheckBot/1.0; +https://ai-builder-2026.web.app)"
META_GRAPH = "https://graph.facebook.com/v25.0"
# Instagram og:description: '143 likes, 0 comments - pibfactcheck on September 13, 2026: "caption..."'
_IG_DESC = re.compile(
    r'^.*?-\s*(?P<handle>[\w.]+) on (?P<date>[A-Z][a-z]+ \d{1,2}, \d{4}):\s*"?(?P<caption>.*?)"?\s*$', re.S)
_VIDEO_PATH = re.compile(r"/(reel|reels|videos?|watch|tv)/|fb\.watch", re.I)
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
    if host in ("threads.net", "threads.com"):
        return "threads"
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
    """Tokenless Meta oEmbed (since June 2026). Used only when the embed carries caption text, which
    it often does not; then the page's Open Graph tags (_page) give caption, author, date and photo."""
    if platform == "instagram":
        endpoint = "instagram_oembed"
    elif platform == "threads":
        endpoint = "threads_oembed"
    else:
        endpoint = "oembed_video" if _VIDEO_PATH.search(url) else "oembed_post"
    token = os.environ.get("META_OEMBED_TOKEN")  # optional: higher rate limits with App Review
    try:
        data = await f.json(f"{META_GRAPH}/{endpoint}?url={quote(url, safe='')}"
                            + (f"&access_token={token}" if token else ""))
    except Exception as e:  # noqa: BLE001
        log.info("meta oembed failed: %s", e)
        return None
    embed = re.sub(r"<script.*?</script>", "", data.get("html") or "", flags=re.S)
    text = _strip_tags(embed)
    if not text or text.lower().startswith("view this post on"):
        return None
    return FetchedPost(source_url=url, platform=platform, text=text,  # type: ignore[arg-type]
                       author_handle=data.get("author_name"), media_missing=True, fetch_method="meta_oembed")


def _instagram_desc(desc: str) -> tuple[str, str | None, datetime | None]:
    """Split Instagram's og:description into (caption, @handle, date)."""
    m = _IG_DESC.match(desc)
    if not m:
        return desc, None, None
    try:
        when = datetime.strptime(m["date"], "%B %d, %Y")
    except ValueError:
        when = None
    return m["caption"].strip(), f"@{m['handle']}", when


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
    published = _date(meta.get("article:published_time") or meta.get("og:published_time"))
    author = meta.get("author") or meta.get("article:author")
    if platform in ("instagram", "facebook", "threads", "x"):
        # Social pages: the caption is the post; trafilatura output is page chrome. A photo post is
        # complete with its og:image; a video post only gives a thumbnail.
        caption = desc or og_title or ""
        if platform == "instagram" and caption:
            caption, ig_handle, ig_date = _instagram_desc(caption)
            author, published = ig_handle or author, ig_date or published
        return FetchedPost(
            source_url=url, platform=platform, title=og_title, text=caption or None,  # type: ignore[arg-type]
            published_at=published, author_handle=author, image_uris=image_uris,
            media_missing=not image_uris or bool(_VIDEO_PATH.search(url)) or "video" in meta.get("og:type", ""),
            fetch_method="open_graph",
        )
    return FetchedPost(
        source_url=url, platform=platform if platform != "other" else "news",  # type: ignore[arg-type]
        title=og_title, text=(f"{desc}\n\n{main}" if desc and main and desc not in main else text),
        published_at=published, author_handle=author,
        image_uris=image_uris, media_missing=False, fetch_method="open_graph" if not main else "html",
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
            elif platform in ("instagram", "facebook", "threads"):
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
