import os

import pytest

from app import settings as st


@pytest.fixture
def clean_env(monkeypatch):
    for key in ["FOO", "BAR", "BAZ", "QUOTED", "CODESPACES", "CODESPACE_NAME", "PUBLIC_BASE_URL",
                "CORS_ORIGINS", "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "FACTCHECK_SKIP_ENV_FILES"]:
        monkeypatch.delenv(key, raising=False)
    st.get_settings.cache_clear()
    yield monkeypatch
    st.get_settings.cache_clear()


def test_env_precedence_environment_then_env_then_defaults(tmp_path, clean_env):
    (tmp_path / ".env.defaults").write_text("FOO=from-defaults\nBAR=from-defaults\nBAZ=from-defaults\n")
    (tmp_path / ".env").write_text("# local override\nexport BAR=from-dotenv\nBAZ=from-dotenv  # note\n"
                                   "QUOTED=\"a b # c\"\n")
    clean_env.setenv("BAZ", "from-environment")
    st.load_env_files(tmp_path)
    assert os.environ["FOO"] == "from-defaults"
    assert os.environ["BAR"] == "from-dotenv"
    assert os.environ["BAZ"] == "from-environment"
    assert os.environ["QUOTED"] == "a b # c"


def test_missing_dotenv_is_fine(tmp_path, clean_env):
    (tmp_path / ".env.defaults").write_text("FOO=x\n")
    st.load_env_files(tmp_path)
    assert os.environ["FOO"] == "x"


def test_skip_flag(tmp_path, clean_env):
    (tmp_path / ".env.defaults").write_text("FOO=x\n")
    clean_env.setenv("FACTCHECK_SKIP_ENV_FILES", "1")
    st.load_env_files(tmp_path)
    assert "FOO" not in os.environ


def test_codespaces_sets_public_url_and_cors(clean_env):
    clean_env.setenv("FACTCHECK_SKIP_ENV_FILES", "1")
    clean_env.setenv("CODESPACES", "true")
    clean_env.setenv("CODESPACE_NAME", "rohit-fluffy-space-abc123")
    clean_env.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    clean_env.setenv("PUBLIC_BASE_URL", "http://localhost:5173")
    s = st.get_settings()
    url = "https://rohit-fluffy-space-abc123-5173.app.github.dev"
    assert s.public_base_url == url
    assert url in s.cors_origins and "http://localhost:5173" in s.cors_origins


def test_outside_codespaces_uses_env(clean_env):
    clean_env.setenv("FACTCHECK_SKIP_ENV_FILES", "1")
    clean_env.setenv("PUBLIC_BASE_URL", "https://example.web.app/")
    clean_env.setenv("CORS_ORIGINS", "https://example.web.app")
    s = st.get_settings()
    assert s.public_base_url == "https://example.web.app"
    assert s.cors_origins == ["https://example.web.app"]
    assert st.codespaces_url(5173) is None
