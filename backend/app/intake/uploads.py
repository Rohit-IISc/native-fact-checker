"""Direct uploads for large shares. Cloud Run rejects request bodies over 32 MB, but a share may be 50 MB, so
the PWA puts big files straight into the media bucket with a short-lived signed URL, then sends the upload id
with POST /v1/checks. The backend reads the object back and treats it exactly like an uploaded file.

Objects live at staged/{uid hash}/{upload id}: the path proves whose upload it is, so no database record is
needed and one user can never submit another user's upload. The media bucket deletes everything after a day
(CLAUDE.md rule 5); a staged object is also deleted as soon as a check has read it.
"""
from __future__ import annotations

import asyncio
import re
from datetime import timedelta

from app.ids import ulid
from app.intake.validate import InvalidInput, UploadedFile
from app.observability.logging import hash_uid
from app.settings import get_config, get_settings

SIGNED_URL_MINUTES = 15
_UPLOAD_ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")  # a ULID, nothing that could walk the bucket
ALLOWED_TYPES = ("image/", "video/", "audio/")


class SigningUnavailable(RuntimeError):
    """Local dev with user credentials cannot sign URLs; the PWA then uploads through the API as before."""


def object_name(uid: str, upload_id: str) -> str:
    return f"staged/{hash_uid(uid)[:16]}/{upload_id}"


def _bucket():
    from google.cloud import storage

    s = get_settings()
    return storage.Client(project=s.gcp_project).bucket(s.media_bucket)


def _sign(name: str, content_type: str) -> str:
    """V4 signed PUT URL. On Cloud Run the service account has no key file, so sign through the IAM
    signBlob API with its access token (api-sa has Service Account Token Creator)."""
    import google.auth
    from google.auth.transport.requests import Request

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    email = getattr(creds, "service_account_email", None)
    if not email or email == "default":
        raise SigningUnavailable("no service account to sign with")
    return _bucket().blob(name).generate_signed_url(
        version="v4", expiration=timedelta(minutes=SIGNED_URL_MINUTES), method="PUT", content_type=content_type,
        service_account_email=email, access_token=creds.token)


async def create(uid: str, content_type: str, size: int) -> dict:
    """A signed URL to PUT one file. Raises InvalidInput for files we would refuse anyway."""
    max_bytes = int(get_config().limits["input"]["max_share_bytes"])
    if size <= 0 or size > max_bytes:
        raise InvalidInput("TOO_LARGE", "Share is over 50 MB")
    if not content_type.startswith(ALLOWED_TYPES):
        raise InvalidInput("UNSUPPORTED_TYPE", "Only images, video and audio can be uploaded")
    if get_settings().store == "memory" or not get_settings().media_bucket:
        raise SigningUnavailable("no media bucket")
    upload_id = ulid()
    url = await asyncio.to_thread(_sign, object_name(uid, upload_id), content_type)
    return {"upload_id": upload_id, "url": url, "method": "PUT", "headers": {"Content-Type": content_type},
            "expires_in_s": SIGNED_URL_MINUTES * 60}


async def read(uid: str, upload_id: str) -> UploadedFile:
    """The uploaded bytes, checked for owner (path) and size before downloading."""
    if not _UPLOAD_ID.match(upload_id or ""):
        raise InvalidInput("UPLOAD_NOT_FOUND", "Unknown upload")
    blob = _bucket().blob(object_name(uid, upload_id))
    try:
        await asyncio.to_thread(blob.reload)
    except Exception as e:  # noqa: BLE001  NotFound, or another user's id: same answer
        raise InvalidInput("UPLOAD_NOT_FOUND", "Upload not found or expired") from e
    if (blob.size or 0) > int(get_config().limits["input"]["max_share_bytes"]):
        raise InvalidInput("TOO_LARGE", "Share is over 50 MB")
    data = await asyncio.to_thread(blob.download_as_bytes)
    return UploadedFile(f"upload-{upload_id}", data, blob.content_type)


async def discard(uid: str, upload_ids: list[str]) -> None:
    """Delete staged objects once read (the check stores its own copy). Best effort: lifecycle cleans up."""
    def _delete() -> None:
        b = _bucket()
        for uid_ in upload_ids:
            try:
                b.blob(object_name(uid, uid_)).delete()
            except Exception:  # noqa: BLE001
                pass

    await asyncio.to_thread(_delete)
