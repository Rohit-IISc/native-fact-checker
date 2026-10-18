from datetime import UTC, datetime, timedelta

from app.cache import tier1
from app.intake.hashing import extract_urls, normalize_text, normalize_url, text_key, url_key


def test_normalize_text_removes_forward_markers_emoji_and_case():
    a = "Forwarded many times\n\n🚨🚨 BREAKING:   Flood in   Bengaluru today!! 🙏"
    b = "breaking: flood in bengaluru today!!"
    assert normalize_text(a) == b
    assert text_key(a) == text_key(b)


def test_normalize_text_keeps_indic_combining_marks():
    hindi = "बेंगलुरु में आज बाढ़"
    assert normalize_text(hindi) == hindi
    assert text_key("फॉरवर्ड किया गया " + hindi) == text_key(hindi)
    kannada = "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಪ್ರವಾಹ"
    assert normalize_text(kannada) == kannada


def test_nfkc_makes_fullwidth_equal():
    assert text_key("ＡＢＣ news") == text_key("abc news")


def test_different_text_different_key():
    assert text_key("Petrol up by Rs 5") != text_key("Petrol up by Rs 15")


def test_empty_text_has_no_key():
    assert text_key("  🙏 🙏 ") is None


def test_normalize_url_strips_tracking_and_www():
    a = "https://www.Example.com/news/story/?utm_source=wa&fbclid=abc&id=7#top"
    assert normalize_url(a) == "https://example.com/news/story?id=7"
    assert url_key(a) == url_key("https://example.com/news/story?id=7")


def test_normalize_url_youtube_mobile_and_si():
    assert url_key("https://m.youtube.com/watch?v=abc&si=xyz") == url_key("https://youtube.com/watch?v=abc")


def test_extract_urls_from_whatsapp_text():
    text = "Dekho ye video (https://youtu.be/abc123), sach hai? Also see https://x.com/a/status/1."
    assert extract_urls(text) == ["https://youtu.be/abc123", "https://x.com/a/status/1"]


async def test_tier1_lookup_respects_status_expiry_and_stubs(store):
    now = datetime.now(UTC)
    await store.set("verdicts", "v1", {"verdict_id": "v1", "status": "ACTIVE", "expires_at": None})
    await store.set("verdicts", "v2", {"verdict_id": "v2", "status": "ACTIVE",
                                       "expires_at": (now - timedelta(days=1)).isoformat()})
    await store.set("verdicts", "v3", {"verdict_id": "v3", "status": "ACTIVE", "is_stub": True})
    await store.set("verdicts", "v4", {"verdict_id": "v4", "status": "SUPERSEDED"})
    await tier1.write(store, ["text:ok"], ["v1"])
    await tier1.write(store, ["text:expired"], ["v2"])
    await tier1.write(store, ["text:stub"], ["v3"])
    await tier1.write(store, ["text:old"], ["v4"])
    await tier1.write(store, ["text:partial"], ["v1", "v2"])

    hit = await tier1.lookup(store, ["text:missing", "text:ok"])
    assert hit["key"] == "text:ok" and [v["verdict_id"] for v in hit["verdicts"]] == ["v1"]
    for key in ("text:expired", "text:stub", "text:old", "text:partial"):
        assert await tier1.lookup(store, [key]) is None, key


async def test_tier1_non_checkable_entry(store):
    await tier1.write(store, ["text:gm"], [], non_checkable={"type": "GREETING", "message": "hi"})
    hit = await tier1.lookup(store, ["text:gm"])
    assert hit["non_checkable"]["type"] == "GREETING"


def test_pinned_demo_verdict_never_expires():
    from datetime import UTC, datetime, timedelta

    from app.cache.tier1 import _usable

    now = datetime.now(UTC)
    past = (now - timedelta(days=1)).isoformat()
    assert not _usable({"status": "ACTIVE", "expires_at": past}, now)
    assert _usable({"status": "ACTIVE", "expires_at": past, "pinned": True}, now)
