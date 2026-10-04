import os

os.environ.update({
    "STORE": "memory",
    "AUTH_MODE": "dev",
    "LLM_MODE": "fake",
    "PIPELINE_MODE": "inline",
    "BIGQUERY_ENABLED": "0",
    "GCP_PROJECT": "",
    "FACTCHECK_SKIP_ENV_FILES": "1",
    "PUBLIC_BASE_URL": "https://factcheck.test",
})
# Running inside a codespace must not change test results (the forwarded URL wins over PUBLIC_BASE_URL).
os.environ.pop("CODESPACES", None)

import pytest  # noqa: E402

from app.fixtures import demo_fixtures  # noqa: E402
from app.llm import FakeLLM, set_llm  # noqa: E402
from app.store import MemoryStore, set_store  # noqa: E402


@pytest.fixture
def store():
    s = MemoryStore()
    set_store(s)
    yield s
    set_store(None)


@pytest.fixture
def llm():
    fake = FakeLLM(demo_fixtures())
    set_llm(fake)
    yield fake
    set_llm(None)
