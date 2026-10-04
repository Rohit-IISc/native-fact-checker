"""Link fetch ladder with mocked HTTP (docs/03 stage 1). No network."""
import io
import json

import httpx
import pytest
from PIL import Image

from app.intake import links

PUBLIC = ["93.184.216.34"]


async def public_resolver(host, port):
    return ["10.0.0.5"] if host.endswith(".internal-corp.test") else PUBLIC


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 10, 10)).save(buf, "JPEG")
    return buf.getvalue()


ARTICLE = """<!doctype html><html><head><title>Fallback title</title>
<meta property="og:title" content="Flood photo is from 2019, not today">
<meta property="og:description" content="A viral photo of a flooded street is old.">
<meta property="og:image" content="/img/flood.jpg">
<meta property="article:published_time" content="2026-09-30T08:00:00+05:30">
</head><body><article><h1>Flood photo is from 2019</h1>
<p>A photo of a flooded street shared on WhatsApp as Bengaluru today was first published in 2019 in Chennai.</p>
<p>Reverse image search shows the earliest copy on a news site from November 2019. The street signs are in Tamil.</p>
<p>Officials said there was no flooding in that area this week. The photo has been shared thousands of times.</p>
</article></body></html>"""

TWEET = {
    "author_url": "https://twitter.com/SomeUser",
    "html": '<blockquote class="twitter-tweet"><p lang="hi" dir="ltr">यह वीडियो आज का है &amp; सच है '
            '<a href="https://t.co/abc">pic.twitter.com/abc</a></p>&mdash; Some User (@SomeUser) '
            '<a href="https://twitter.com/SomeUser/status/1?ref_src=x">October 3, 2026</a></blockquote>',
}


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if u.startswith("https://news.example.com/story"):
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=ARTICLE)
    if u == "https://news.example.com/img/flood.jpg":
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=jpeg())
    if u.startswith("https://publish.twitter.com/oembed"):
        return httpx.Response(200, json=TWEET)
    if u.startswith("https://www.youtube.com/oembed"):
        return httpx.Response(200, json={"title": "Old flood video", "author_name": "Some Channel"})
    if u == "https://bit.ly/x1":
        return httpx.Response(301, headers={"location": "https://x.com/SomeUser/status/1"})
    if u == "https://x.com/SomeUser/status/1":
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")
    if u == "https://evil.example.com/r":
        return httpx.Response(302, headers={"location": "http://metadata.internal-corp.test/secret"})
    if u == "https://big.example.com/":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>" + b"a" * (6 * 1024 * 1024))
    return httpx.Response(404)


async def fetch(url, **kw):
    stored = []

    async def store_image(data, mime):
        stored.append((len(data), mime))
        return f"gs://bucket/c1/link.{mime.split('/')[-1]}"

    post = await links.fetch(url, store_image=store_image, transport=httpx.MockTransport(handler),
                             resolver=public_resolver, **kw)
    return post, stored


@pytest.mark.parametrize("url,platform", [
    ("https://youtu.be/abc", "youtube"), ("https://www.youtube.com/shorts/abc", "youtube"),
    ("https://x.com/a/status/1", "x"), ("https://mobile.twitter.com/a/status/1", "x"),
    ("https://www.instagram.com/p/abc/", "instagram"), ("https://fb.watch/abc", "facebook"),
    ("https://t.me/channel/5", "telegram"), ("https://www.thehindu.com/news/x", "other"),
])
def test_platform_detection(url, platform):
    assert links.platform_of(url) == platform


async def test_news_article_gets_text_title_date_and_image():
    post, stored = await fetch("https://news.example.com/story?utm_source=wa")
    assert post.fetch_method == "html" and post.platform == "news"
    assert post.title == "Flood photo is from 2019, not today"
    assert "first published in 2019 in Chennai" in post.text
    assert post.published_at.year == 2026 and post.published_at.month == 9
    assert post.image_uris == ["gs://bucket/c1/link.jpeg"] and stored[0][1] == "image/jpeg"
    assert post.media_missing is False


async def test_x_post_via_oembed_flags_missing_media():
    post, _ = await fetch("https://x.com/SomeUser/status/1")
    assert post.fetch_method == "x_oembed" and post.platform == "x"
    assert post.text.startswith("यह वीडियो आज का है & सच है")
    assert post.author_handle == "@SomeUser" and post.published_at.day == 3
    assert post.media_missing is True


async def test_youtube_passes_url_to_gemini():
    post, _ = await fetch("https://youtu.be/abc")
    assert post.youtube_url == "https://youtu.be/abc" and post.title == "Old flood video"
    assert post.fetch_method == "youtube"


async def test_short_link_resolves_to_platform():
    post, _ = await fetch("https://bit.ly/x1")
    assert post.platform == "x" and post.fetch_method == "x_oembed"


async def test_redirect_to_private_address_is_blocked():
    post, _ = await fetch("https://evil.example.com/r")
    assert post.fetch_method == "failed"


async def test_oversized_page_fails_cleanly():
    post, _ = await fetch("https://big.example.com/")
    assert post.fetch_method == "failed"


async def test_non_http_scheme_fails_cleanly():
    post, _ = await fetch("file:///etc/passwd")
    assert post.fetch_method == "failed"


async def test_unreadable_link_asks_for_screenshot_and_refunds_quota(store, llm, monkeypatch):
    from app.main import app
    from app.models import FetchedPost
    from app.pipeline.dispatch import drain

    async def failed(url, **_):
        return FetchedPost(source_url=url, platform="instagram", media_missing=True, fetch_method="failed")

    monkeypatch.setattr(links, "fetch", failed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        h = {"Authorization": "Bearer dev:alice"}
        r = await c.post("/v1/checks", headers=h, data={"text": "https://www.instagram.com/reel/abc/"})
        assert r.status_code == 202
        await drain()
        doc = (await c.get(f"/v1/checks/{r.json()['check_id']}", headers=h)).json()
        assert doc["status"] == "DONE" and doc["result"]["media_missing_prompt"] is True
        assert doc["result"]["claims"] == [] and doc["error_code"] == "LINK_UNREADABLE"
        assert (await c.get("/v1/me/quota", headers=h)).json()["used"] == 0
        assert json.dumps(doc)  # serializable


async def test_extractor_never_called_without_content(llm):
    from app.agents import extractor
    from app.models import CheckRequest, FetchedPost

    req = CheckRequest(check_id="c", uid="u", text="  ", url="https://x.com/a/status/1", share_date="2026-10-04")
    empty = FetchedPost(source_url=req.url, platform="x", fetch_method="x_oembed")
    result = await extractor.extract(llm, req, empty)
    assert result.checkable is False and result.non_checkable_type.value == "OTHER"
    assert "extractor" not in llm.prompts  # no model call
