"""Day 0: confirm every model ID in config/models.yaml answers on Vertex AI.

Usage: make check-models (GCP_PROJECT from env, backend/.env or backend/.env.defaults)
Sends one tiny request per model (a fraction of a cent). Prints the first working
ID for each key so you can update config/models.yaml.
"""
import sys
from pathlib import Path

import yaml
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.settings import get_settings  # noqa: E402

cfg = yaml.safe_load(open(ROOT / "config" / "models.yaml"))
project = get_settings().gcp_project
client = genai.Client(vertexai=True, project=project, location=cfg["vertex"]["location"])

ok = True
for key in ("flash", "pro"):
    m = cfg["models"][key]
    found = None
    for model_id in [m["id"], *m.get("fallbacks", [])]:
        try:
            client.models.generate_content(
                model=model_id, contents="Reply with OK",
                config=types.GenerateContentConfig(max_output_tokens=16),
            )
            found = model_id
            break
        except Exception as e:  # noqa: BLE001
            print(f"  {key}: {model_id} not available ({type(e).__name__}: {str(e)[:120]})")
    print(f"{key}: {found or 'NONE WORKING'}")
    ok &= found is not None

try:
    client.models.embed_content(
        model=cfg["models"]["embedding"]["id"], contents="test",
        config=types.EmbedContentConfig(output_dimensionality=cfg["models"]["embedding"]["dims"]),
    )
    print(f"embedding: {cfg['models']['embedding']['id']}")
except Exception as e:  # noqa: BLE001
    print(f"embedding: FAILED ({e})")
    ok = False

print("TTS: test separately with backend/app/output/tts.py --say 'नमस्ते' --lang hi-IN")
sys.exit(0 if ok else 1)
