"""Unit tests for src/config/settings.py."""


def test_llm_settings_defaults(monkeypatch):
    # Given: no LLM env vars and no .env loaded
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from config.settings import LLMSettings

    # When: instantiated with _env_file=None so .env is ignored
    s = LLMSettings(_env_file=None)

    # Then: defaults are applied
    assert s.model == "gpt-4.1-mini"
    assert s.api_key == ""


def test_llm_settings_service_url_alias(monkeypatch):
    # Given: LLM_SERVICE_URL is set (alias for base_url)
    monkeypatch.setenv("LLM_SERVICE_URL", "https://my-proxy.example.com")

    # When: LLMSettings is instantiated fresh
    from config import settings as settings_module

    settings_module._settings = None
    from config.settings import LLMSettings

    s = LLMSettings()

    # Then: base_url reflects the alias
    assert s.base_url == "https://my-proxy.example.com"


def test_graph_settings_default_max_iterations():
    # Given / When
    from config.settings import GraphSettings

    s = GraphSettings()

    # Then
    assert s.max_iterations == 15


def test_database_settings_env_var(monkeypatch):
    # Given
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")

    # When
    from config.settings import DatabaseSettings

    s = DatabaseSettings()

    # Then
    assert s.database_url == "postgresql://user:pass@host:5432/db"


def test_database_settings_metadata_schema_default():
    # Given / When
    from config.settings import DatabaseSettings

    s = DatabaseSettings()

    # Then
    assert s.metadata_schema == "agent_metadata"


def test_sql_safety_defaults():
    # Given / When
    from config.settings import SQLSafetySettings

    s = SQLSafetySettings()

    # Then
    assert s.max_rows == 100
    assert s.timeout_seconds == 30


def test_streamlit_settings_defaults(monkeypatch):
    # Given: no overrides for Streamlit settings
    monkeypatch.delenv("STREAMLIT_PORT", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)

    from config.settings import StreamlitSettings

    # When: instantiated with _env_file=None so .env is ignored
    s = StreamlitSettings(_env_file=None)

    # Then
    assert s.streamlit_port == 8501
    assert s.api_base_url == "http://localhost:8000"


def test_get_settings_singleton():
    # Given
    from config import settings as settings_module

    settings_module._settings = None

    # When
    from config.settings import get_settings

    s1 = get_settings()
    s2 = get_settings()

    # Then: same instance returned both times
    assert s1 is s2

    # Clean up
    settings_module._settings = None


def test_settings_composes_all_sub_settings():
    # Given
    from config import settings as settings_module

    settings_module._settings = None

    # When
    from config.settings import get_settings

    s = get_settings()

    # Then: all sub-settings are accessible
    assert hasattr(s, "llm")
    assert hasattr(s, "langsmith")
    assert hasattr(s, "graph")
    assert hasattr(s, "db")
    assert hasattr(s, "app")
    assert hasattr(s, "sql")
    assert hasattr(s, "ui")

    # Clean up
    settings_module._settings = None
