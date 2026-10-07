"""make smoke: real checks through Pub/Sub -> Cloud Run on the deployed service, then clean up.

Wave 1: Tamil text, Hindi text, Hindi image, news link, Instagram link (the full pipeline, unless an
earlier run's verdict is still cached). Wave 2: a reworded English repeat of the Hindi claim, which
should come from the tier 2 cache. Prints label, latency, agents and stage errors per check.

Writes to the production database as uid "deploy-smoke" and always deletes what it created: its checks,
history rows, and only the verdicts (and claim embeddings) its own checks created. Verdicts reused from
the cache belong to other checks and are never touched. Costs about $0.40.
Usage (from backend/): PYTHONPATH=. uv run python ../scripts/smoke_prod.py
"""
import hashlib
import json
import time
from datetime import UTC, datetime

import httpx
from google.cloud import firestore, pubsub_v1, storage
from google.cloud.firestore_v1.base_query import FieldFilter

from app.ids import ulid
from app.intake.media import image_phash
from app.settings import get_settings

P = get_settings().gcp_project
UID = "deploy-smoke"
db = firestore.Client(project=P, database="(default)")
pub = pubsub_v1.PublisherClient()
IMG = open(__file__.rsplit("/scripts/", 1)[0] + "/tests/acceptance/media/hi-free-laptop-scheme.jpg", "rb").read()
WAVE1 = {
    "ta-text": {"text": "சூடான தண்ணீரில் எலுமிச்சை சாறு கலந்து குடித்தால் கொரோனா வைரஸ் அழியும். அனைவருக்கும் பகிருங்கள்!"},
    "hi-text": {"text": "प्रधानमंत्री मोदी सभी भारतीयों को 3 महीने का मुफ्त मोबाइल रिचार्ज दे रहे हैं। "
                        "नीचे दिए गए लिंक पर क्लिक करके अभी अपना रिचार्ज पाएं!"},
    "hi-image": {"image": True},
    "news-link": {"url": "https://www.bbc.com/news/world-asia-india-66594520"},
    "insta-link": {"url": "https://www.instagram.com/p/DeEcaQtk3LR/"},
}
WAVE2 = {"tier2-repeat": {"text": "The Prime Minister is offering every Indian three months of free phone recharge. "
                                  "Click the link to claim it today!"}}


def start(spec):
    cid = ulid()
    media = []
    if spec.get("image"):
        n = f"{cid}/0.jpeg"
        storage.Client(project=P).bucket(f"{P}-media").blob(n).upload_from_string(IMG, content_type="image/jpeg")
        media = [{"kind": "image", "mime_type": "image/jpeg", "uri": f"gs://{P}-media/{n}", "size_bytes": len(IMG),
                  "sha256": hashlib.sha256(IMG).hexdigest(), "phash": image_phash(IMG)}]
    req = {"check_id": cid, "uid": UID, "text": spec.get("text") or spec.get("url"), "url": spec.get("url"),
           "media": media, "client_lang": "en", "share_date": datetime.now(UTC).date().isoformat()}
    db.collection("checks").document(cid).set({
        "check_id": cid, "uid": UID, "status": "RUNNING", "stage": "received",
        "created_at": datetime.now(UTC).isoformat(), "request": req, "cache_keys": [], "agents": {}})
    pub.publish(pub.topic_path(P, "check-jobs"), json.dumps({"check_id": cid}).encode()).result()
    return cid


def wait(ids):
    t0, done = time.time(), {}
    while len(done) < len(ids) and time.time() - t0 < 240:
        for n, cid in ids.items():
            if n not in done:
                d = db.collection("checks").document(cid).get().to_dict() or {}
                # Audio is written after DONE; wait for it so cleanup never races the audio write.
                if d.get("status") == "FAILED" or (d.get("status") == "DONE"
                                                   and not (d.get("result") or {}).get("audio_pending")):
                    done[n] = d
        time.sleep(2)
    return done


def report(n, d):
    r = d.get("result") or {}
    labels = [c["label"] for c in r.get("claims", [])] or [r.get("non_checkable_type")]
    print(f"{n:<12} {d.get('status')} tier={r.get('cache_tier_hit')} latency={d.get('latency_ms')}ms "
          f"lang={d.get('content_language')} labels={labels} agents={d.get('agents')} "
          f"errors={d.get('stage_errors') or d.get('error_detail')}")
    for c in r.get("claims", [])[:1]:
        print(f"             headline: {c['answer']['headline']}")
        if c.get("audio_url"):
            a = httpx.get(c["audio_url"].replace(get_settings().public_base_url, f"https://{P}.web.app"), timeout=20)
            kind = a.headers.get("content-type")
            print(f"             audio: HTTP {a.status_code} {kind} {len(a.content) // 1024} KB")
        else:
            print("             audio: none")
        print(f"             sources: {[(e.get('publisher'), e['tier']) for e in c['evidence'][:4]]}")


def cleanup(check_ids: list[str]) -> None:
    mine = set(check_ids)
    outputs = storage.Client(project=P).bucket(get_settings().outputs_bucket)
    for cid in check_ids:
        for v in db.collection("verdicts").where(filter=FieldFilter("check_id", "==", cid)).stream():
            if (v.to_dict() or {}).get("check_id") in mine:  # created by our check, not reused from cache
                for cd in db.collection("claims").where(filter=FieldFilter("verdict_id", "==", v.id)).stream():
                    cd.reference.delete()
                for blob in outputs.list_blobs(prefix=f"audio/{v.id}_"):
                    blob.delete()
                v.reference.delete()
        db.collection("checks").document(cid).delete()
        db.collection("users").document(UID).collection("history").document(cid).delete()


started: list[str] = []
try:
    ids1 = {n: start(s) for n, s in WAVE1.items()}
    started += ids1.values()
    done1 = wait(ids1)
    ids2 = {n: start(s) for n, s in WAVE2.items()}
    started += ids2.values()
    done2 = wait(ids2)
    for n in ids1:
        report(n, done1.get(n, {}))
    for n in ids2:
        report(n, done2.get(n, {}))
finally:
    cleanup(started)
    print(f"cleaned up {len(started)} checks")
