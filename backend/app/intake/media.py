"""Media lane: probe, fingerprint and store uploaded files (docs/03 stage 0, docs/04 tier 1).

Fingerprints are computed before the tier 1 lookup; files are stored only on a cache miss.
Storage is GCS `{project}-media/{check_id}/` (24 h lifecycle) with STORE=firestore, and a local
temp dir with STORE=memory (tests, offline UI), whose paths the extractor sends inline.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.intake.hashing import sha256_hex
from app.intake.validate import UploadedFile
from app.models import MediaRef
from app.settings import get_config, get_settings

log = logging.getLogger(__name__)
LOCAL_MEDIA_DIR = Path(tempfile.gettempdir()) / "factcheck-media"


@dataclass
class IngestedFile:
    file: UploadedFile
    kind: str
    mime_type: str
    sha256: str
    duration_s: float | None = None
    phash: str | None = None                      # images
    frame_phashes: list[str] = field(default_factory=list)  # video keyframes

    @property
    def trimmed(self) -> bool:
        limit = float(get_config().limits["input"]["max_media_seconds"])
        return bool(self.duration_s and self.duration_s > limit)


def image_phash(data: bytes) -> str | None:
    """64-bit pHash as 16 hex chars, or None if Pillow cannot decode (HEIC: exact hash only)."""
    import imagehash
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            return str(imagehash.phash(img.convert("RGB")))
    except Exception:  # noqa: BLE001
        return None


async def _run(*args: str, stdin: bytes | None = None, limit_s: float = 30) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout=limit_s)
    except TimeoutError:
        proc.kill()
        raise
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} exited {proc.returncode}")
    return out


async def probe_duration(path: Path) -> float | None:
    try:
        out = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path))
        return float(json.loads(out)["format"]["duration"])
    except Exception as e:  # noqa: BLE001  unknown duration: the extractor's end offset still caps it
        log.warning("ffprobe failed: %s", e)
        return None


async def video_frame_phashes(path: Path, every_s: float, max_s: float) -> list[str]:
    """pHash of one frame every `every_s` seconds over the first `max_s` seconds."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            await _run("ffmpeg", "-v", "error", "-t", str(max_s), "-i", str(path),
                       "-vf", f"fps=1/{every_s},scale=256:-2", f"{tmp}/f%03d.jpg", limit_s=60)
        except Exception as e:  # noqa: BLE001
            log.warning("ffmpeg keyframes failed: %s", e)
            return []
        return await asyncio.to_thread(_hash_frames, Path(tmp))


def _hash_frames(folder: Path) -> list[str]:
    return [h for f in sorted(folder.glob("f*.jpg")) if (h := image_phash(f.read_bytes()))]


async def fingerprint(typed: list[tuple[UploadedFile, str, str]]) -> list[IngestedFile]:
    """Hash, pHash and probe every file. Video and audio go through a temp file for ffmpeg."""
    lim = get_config().limits
    out = []
    for f, kind, mime in typed:
        item = IngestedFile(file=f, kind=kind, mime_type=mime, sha256=sha256_hex(f.data))
        if kind == "image":
            item.phash = await asyncio.to_thread(image_phash, f.data)
        else:
            with tempfile.NamedTemporaryFile(suffix=Path(f.filename).suffix or ".bin") as tmp:
                tmp.write(f.data)
                tmp.flush()
                item.duration_s = await probe_duration(Path(tmp.name))
                if kind == "video":
                    item.frame_phashes = await video_frame_phashes(
                        Path(tmp.name), float(lim["cache"]["video_keyframe_every_s"]),
                        float(lim["input"]["max_media_seconds"]),
                    )
        out.append(item)
    return out


def _object_name(check_id: str, i: int, item: IngestedFile) -> str:
    ext = item.mime_type.split("/")[-1].replace("quicktime", "mov").replace("mpeg", "mp3")
    return f"{check_id}/{i}.{ext}"


async def store(check_id: str, items: list[IngestedFile]) -> list[MediaRef]:
    """Persist files and return MediaRefs for the CheckRequest."""
    s = get_settings()
    refs = []
    for i, item in enumerate(items):
        name = _object_name(check_id, i, item)
        if s.store == "memory" or not s.media_bucket:
            path = LOCAL_MEDIA_DIR / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item.file.data)
            uri = str(path)
        else:
            await asyncio.to_thread(_upload_gcs, s.media_bucket, name, item.file.data, item.mime_type)
            uri = f"gs://{s.media_bucket}/{name}"
        refs.append(MediaRef(
            kind=item.kind, mime_type=item.mime_type, uri=uri, size_bytes=len(item.file.data),
            sha256=item.sha256, duration_s=item.duration_s, phash=item.phash, frame_phashes=item.frame_phashes,
        ))
    return refs


async def store_link_image(check_id: str, data: bytes, mime: str) -> str:
    """og:image of a shared link, stored next to the uploads. Returns its URI for the extractor."""
    s = get_settings()
    name = f"{check_id}/link-{sha256_hex(data)[:12]}.{mime.split('/')[-1]}"
    if s.store == "memory" or not s.media_bucket:
        path = LOCAL_MEDIA_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
    await asyncio.to_thread(_upload_gcs, s.media_bucket, name, data, mime)
    return f"gs://{s.media_bucket}/{name}"


_gcs = None


def _upload_gcs(bucket: str, name: str, data: bytes, mime: str) -> None:
    global _gcs
    if _gcs is None:
        from google.cloud import storage

        _gcs = storage.Client(project=get_settings().gcp_project)
    _gcs.bucket(bucket).blob(name).upload_from_string(data, content_type=mime)


def clear_local_media() -> None:
    shutil.rmtree(LOCAL_MEDIA_DIR, ignore_errors=True)
