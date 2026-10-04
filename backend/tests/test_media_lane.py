"""Media lane: upload, fingerprints, tier 1 exact and near-exact hits (docs/03 stage 0, docs/04)."""
import io
import shutil
import subprocess

import httpx
import pytest
from PIL import Image, ImageDraw

from app.cache import tier1
from app.intake import media
from app.main import app
from app.pipeline.dispatch import drain

AUTH = {"Authorization": "Bearer dev:alice"}
BOB = {"Authorization": "Bearer dev:bob"}


def picture(seed: int = 0, size: int = 400, quality: int = 90) -> bytes:
    img = Image.new("RGB", (size, size), (240, 230, 200))
    d = ImageDraw.Draw(img)
    for i in range(6):
        x = (37 * (i + 1) * (seed + 3)) % (size - 80)
        d.rectangle([x, i * size // 7, x + 80, i * size // 7 + 40], fill=((50 * i + seed * 90) % 255, 40, 120))
    d.ellipse([size // 3, size // 3, size // 2 + 60, size // 2 + 60], fill=(20, 120, 60))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def resized(data: bytes, size: int, quality: int) -> bytes:
    img = Image.open(io.BytesIO(data)).resize((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


@pytest.fixture
async def client(store, llm):
    media.clear_local_media()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def share(client, data: bytes, name="photo.jpg", mime="image/jpeg", headers=AUTH, **form):
    return await client.post("/v1/checks", headers=headers, data=form, files={"files": (name, data, mime)})


def test_hamming_and_chunks():
    assert tier1.hamming("ffff000000000000", "fffe000000000001") == 2
    assert tier1._chunks("0123456789abcdef") == ["00123", "14567", "289ab", "3cdef"]


def test_phash_survives_resize_and_recompression():
    a = picture()
    b = resized(a, 300, 55)
    assert a != b
    assert tier1.hamming(media.image_phash(a), media.image_phash(b)) <= 6
    assert tier1.hamming(media.image_phash(a), media.image_phash(picture(seed=5))) > 6


async def test_image_is_stored_and_reaches_the_pipeline(client, store, llm):
    r = await share(client, picture(), text="Is this true?")
    assert r.status_code == 202
    await drain()
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["input_types"] == ["text", "image"]
    m = doc["request"]["media"][0]
    assert m["kind"] == "image" and m["mime_type"] == "image/jpeg" and len(m["phash"]) == 16
    assert m["uri"].startswith(str(media.LOCAL_MEDIA_DIR))  # memory store keeps files locally
    assert doc["status"] == "DONE"


async def test_same_image_new_caption_hits_tier1_for_another_user(client):
    # The fake extractor marks a share with no text as not checkable, which is always cached.
    first = await share(client, picture())
    await drain()
    assert first.status_code == 202
    again = await share(client, picture(), headers=BOB, text="नया कैप्शन")
    assert again.status_code == 200 and again.json()["cache_tier_hit"] == "T1"


async def test_near_duplicate_image_hits_tier1(client):
    await share(client, picture())
    await drain()
    edited = resized(picture(), 320, 60)
    r = await share(client, edited)
    assert r.status_code == 200 and r.json()["cache_tier_hit"] == "T1"


async def test_different_image_misses(client):
    await share(client, picture())
    await drain()
    r = await share(client, picture(seed=7))
    assert r.status_code == 202


async def test_long_video_is_flagged_trimmed(client, store, monkeypatch):
    async def long_probe(_path):
        return 240.0

    async def no_frames(*_a):
        return []

    monkeypatch.setattr(media, "probe_duration", long_probe)
    monkeypatch.setattr(media, "video_frame_phashes", no_frames)
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
    r = await share(client, mp4, name="v.mp4", mime="video/mp4")
    assert r.status_code == 202
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["media_trimmed"] is True and doc["request"]["media"][0]["duration_s"] == 240.0


@pytest.fixture
def two_encodings(tmp_path) -> tuple[bytes, bytes]:
    """The same 12 s clip, and a smaller re-encode of it (what a WhatsApp re-forward looks like)."""
    src, smaller = tmp_path / "a.mp4", tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=12:size=320x240:rate=10",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", "scale=240:180", "-b:v", "150k", str(smaller)],
                   check=True)
    return src.read_bytes(), smaller.read_bytes()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
async def test_reencoded_video_hits_tier1(client, two_encodings):
    original, reencoded = two_encodings
    first = await share(client, original, name="a.mp4", mime="video/mp4")
    assert first.status_code == 202
    await drain()
    r = await share(client, reencoded, name="b.mp4", mime="video/mp4")
    assert r.status_code == 200 and r.json()["cache_tier_hit"] == "T1"
