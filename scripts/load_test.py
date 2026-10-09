"""Load test on production (eval/TESTS-TO-DO.md section 4): N different checks at once, for N in 3, 5, 10.

Same path and cleanup as make smoke (uid "deploy-smoke", env "smoke" in BigQuery): checks go through
Pub/Sub to Cloud Run, and everything a wave created is deleted before the next wave, so no claim is
answered from the cache. Reports latency, failed agents and Vertex 429s per wave.
Costs about 0.13 USD per check (18 checks: about 2.50 USD).
Usage (from backend/): PYTHONPATH=. uv run python ../scripts/load_test.py [--waves 3,5,10]
"""
import argparse
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import smoke_prod as smoke  # noqa: E402

# Ten widely forwarded hoaxes (already debunked), five languages, so every check runs the full pipeline.
CLAIMS = [
    "प्रधानमंत्री मोदी सभी भारतीयों को 3 महीने का मुफ्त मोबाइल रिचार्ज दे रहे हैं। लिंक पर क्लिक करें!",
    "सरकार हर लड़की को प्रधानमंत्री कन्या आशीर्वाद योजना के तहत 2000 रुपये दे रही है।",
    "2000 रुपये के नए नोट में GPS नैनो चिप लगी है जिससे नोट को ट्रैक किया जा सकता है।",
    "சூடான தண்ணீரில் எலுமிச்சை சாறு கலந்து குடித்தால் கொரோனா வைரஸ் அழியும்.",
    "செப்டம்பர் 1 முதல் ATMகளில் 500 ரூபாய் நோட்டு வழங்கப்படாது என்று ரிசர்வ் வங்கி அறிவித்துள்ளது.",
    "200 ರೂಪಾಯಿ ನೋಟಿನ ಮೇಲೆ ಗಾಂಧಿ ಬದಲು ಶಿವಾಜಿ ಫೋಟೋ ಬರಲಿದೆ ಎಂದು ಆರ್‌ಬಿಐ ಘೋಷಿಸಿದೆ.",
    "Vaksin COVID-19 mengandung microchip untuk melacak orang yang divaksin.",
    "WEF berencana memasukkan vaksin ke dalam air minum.",
    "NASA confirmed that the Earth will experience 15 days of total darkness in November.",
    "UNESCO declared the Indian national anthem the best anthem in the world.",
]


def log_429s(since: str) -> int:
    q = (f'resource.type="cloud_run_revision" AND resource.labels.service_name="factcheck-api" '
         f'AND (textPayload:"429" OR jsonPayload.message:"429" OR jsonPayload.reason:"429") '
         f'AND timestamp>="{since}"')
    out = subprocess.run(["gcloud", "logging", "read", q, "--format=value(timestamp)", "--limit=1000",
                          f"--project={smoke.P}"], capture_output=True, text=True).stdout
    return len([x for x in out.splitlines() if x.strip()])


def wave(n: int) -> dict:
    since = datetime.now(UTC).isoformat()
    started = []
    try:
        ids = {f"c{i}": smoke.start({"text": CLAIMS[i % len(CLAIMS)]}) for i in range(n)}
        started += ids.values()
        t0 = time.time()
        done = smoke.wait(ids)
        wall = time.time() - t0
    finally:
        smoke.cleanup(started)
    lat = sorted(d.get("latency_ms") or 0 for d in done.values() if d.get("status") == "DONE")
    degraded = sum(1 for d in done.values() if d.get("missing_lanes") or d.get("stage_errors"))
    return {
        "n": n, "done": len(lat), "failed": n - len(lat),
        "p50_s": round(statistics.median(lat) / 1000, 1) if lat else None,
        "max_s": round(lat[-1] / 1000, 1) if lat else None,
        "over_90s": sum(1 for x in lat if x > 90_000), "degraded": degraded,
        "wall_s": round(wall), "log_429s": log_429s(since),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--waves", default="3,5,10")
    a = ap.parse_args()
    print("concurrent  done  failed  p50     max     >90s  degraded  wall    429s in logs")
    for n in (int(x) for x in a.waves.split(",")):
        r = wave(n)
        print(f"{r['n']:>10}  {r['done']:>4}  {r['failed']:>6}  {r['p50_s']!s:>5}s  {r['max_s']!s:>5}s  "
              f"{r['over_90s']:>4}  {r['degraded']:>8}  {r['wall_s']:>4}s  {r['log_429s']:>6}")
        time.sleep(60)  # let quota recover a little between waves


if __name__ == "__main__":
    main()
