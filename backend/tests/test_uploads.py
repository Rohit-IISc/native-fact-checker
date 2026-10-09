"""Direct uploads for shares over Cloud Run's 32 MB limit: owner scoping, limits, and a check that reads one."""
import httpx
import pytest

from app.intake import uploads
from app.intake.validate import InvalidInput
from app.main import app
from app.pipeline.dispatch import drain

AUTH = {"Authorization": "Bearer dev:alice"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
UID = "01M4ABCDEFGHJKMNPQRSTVWXYZ"


class FakeBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.size, self.content_type = None, None

    def reload(self):
        if self.name not in self.store:
            raise RuntimeError("404")
        self.size, self.content_type = len(self.store[self.name]), "image/jpeg"

    def download_as_bytes(self):
        return self.store[self.name]

    def delete(self):
        self.store.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return FakeBlob(self.objects, name)


@pytest.fixture
def bucket(monkeypatch):
    b = FakeBucket()
    monkeypatch.setattr(uploads, "_bucket", lambda: b)
    return b


def test_object_path_is_scoped_to_the_user():
    assert uploads.object_name("alice", UID) != uploads.object_name("bob", UID)
    assert uploads.object_name("alice", UID).startswith("staged/") and UID in uploads.object_name("alice", UID)


@pytest.mark.parametrize("ctype,size,code", [("video/mp4", 60 * 1024 * 1024, "TOO_LARGE"),
                                              ("video/mp4", 0, "TOO_LARGE"),
                                              ("application/pdf", 1000, "UNSUPPORTED_TYPE")])
async def test_create_refuses_what_a_check_would_refuse(ctype, size, code):
    with pytest.raises(InvalidInput) as e:
        await uploads.create("alice", ctype, size)
    assert e.value.error_code == code


async def test_bad_or_foreign_upload_ids_are_not_found(bucket):
    bucket.objects[uploads.object_name("bob", UID)] = JPEG
    for uid, upload_id in [("alice", "../../etc"), ("alice", UID)]:  # path tricks, and bob's upload
        with pytest.raises(InvalidInput) as e:
            await uploads.read(uid, upload_id)
        assert e.value.error_code == "UPLOAD_NOT_FOUND"
    assert (await uploads.read("bob", UID)).data == JPEG


async def test_signing_unavailable_in_dev_falls_back(store):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/uploads", headers=AUTH, json={"content_type": "video/mp4", "size": 40_000_000})
    assert r.status_code == 501 and r.json()["error_code"] == "DIRECT_UPLOAD_UNAVAILABLE"


async def test_check_reads_a_staged_upload_and_discards_it(store, llm, bucket):
    name = uploads.object_name("alice", UID)
    bucket.objects[name] = JPEG
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/checks", headers=AUTH, data={"upload_ids": [UID]})
        await drain()
    assert r.status_code in (200, 202), r.text
    doc = await store.get("checks", r.json()["check_id"])
    assert doc["request"]["media"][0]["kind"] == "image"
    assert name not in bucket.objects
