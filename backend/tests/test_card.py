"""Correction card: drawn by code in the answer language, served (and kept) by the API."""
import io

import httpx
import pytest
from PIL import Image

from app.main import app
from app.models import Label
from app.output import card
from app.pipeline.dispatch import drain
from tests.card_samples import BY_LANGUAGE, sample_claim

AUTH = {"Authorization": "Bearer dev:alice"}


@pytest.mark.parametrize("language", [f"{k}-ID" if k == "id" else f"{k}-IN" for k in BY_LANGUAGE])
def test_card_renders_in_every_demo_language(language):
    png = card.render(sample_claim(language, Label.FALSE))
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.size == (card.W, card.H)
    assert img.getpixel((10, 10)) == (0xC6, 0x28, 0x28)  # FALSE red band


def test_card_sources_skip_social_media_and_repeat_publishers():
    assert card.top_sources(sample_claim("en-IN")) == ["BOOM", "The Hindu"]


def test_long_text_is_cut_with_an_ellipsis_within_the_width():
    from PIL import ImageDraw

    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = card.Fonts("NotoSansDevanagari", 44)
    lines = card._wrap(d, "सच " * 400, font, 900, 3)
    assert len(lines) == 3 and lines[-1].endswith(" …")
    assert all(font.length(d, ln) <= 900 for ln in lines)


def test_latin_words_in_an_indic_card_use_the_latin_font():
    """Oct 16: "CHCKR" and "DELHI" drew as empty boxes with the Devanagari font."""
    f = card.Fonts("NotoSansDevanagari", 40)
    runs = f.runs("“DELHI संकट मे” CHCKR 2022")
    assert [(t, fo is f.latin) for t, fo in runs] == [
        ("“DELHI ", True), ("संकट मे” ", False), ("CHCKR 2022", True)]
    assert card.Fonts("NotoSans", 40).runs("Delhi floods") == [("Delhi floods", card.Fonts("NotoSans", 40).latin)]


async def test_card_is_drawn_on_request_and_linked_from_the_result(store, llm):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/checks", headers=AUTH, data={"text": "सरकार सभी को मुफ्त लैपटॉप दे रही है"})
        await drain()
        claim = (await store.get("checks", r.json()["check_id"]))["result"]["claims"][0]
        assert claim["card_url"].endswith(f"/api/v1/results/{claim['verdict_id']}/card?lang=hi-IN")
        got = await c.get(f"/v1/results/{claim['verdict_id']}/card", params={"lang": "hi-IN"})
        assert got.status_code == 200 and got.headers["content-type"] == "image/png"
        assert await card.read_card(claim["verdict_id"], "hi-IN") == got.content  # kept for the next request


async def test_missing_card_is_404(store):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/v1/results/nope/card", params={"lang": "hi-IN"})
    assert r.status_code == 404
