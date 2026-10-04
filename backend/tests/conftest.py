import os

os.environ.update({
    "STORE": "memory",
    "AUTH_MODE": "dev",
    "LLM_MODE": "fake",
    "PIPELINE_MODE": "inline",
    "BIGQUERY_ENABLED": "0",
    "GCP_PROJECT": "",
    "PUBLIC_BASE_URL": "https://factcheck.test",
})

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
