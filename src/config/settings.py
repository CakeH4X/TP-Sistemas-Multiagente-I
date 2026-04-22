"""Application settings using pydantic-settings.

Centralizes all runtime configuration. Other modules import from here
instead of reading environment variables directly.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM service configuration (LiteLLM proxy)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LLM_",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str = Field(
        default="https://sa-llmproxy.it.itba.edu.ar",
        description="Base URL of the LiteLLM proxy.",
        validation_alias=AliasChoices("LLM_BASE_URL", "LLM_SERVICE_URL"),
    )
    api_key: str = Field(default="", description="API key for the LLM service.")
    model: str = Field(default="gpt-4.1-mini", description="Model identifier.")


class LangSmithSettings(BaseSettings):
    """LangSmith observability settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LANGSMITH_",
        case_sensitive=False,
        extra="ignore",
    )

    tracing: bool = Field(default=False, description="Enable LangSmith tracing.")
    endpoint: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith API endpoint.",
    )
    api_key: str = Field(default="", description="LangSmith API key.")
    project: str = Field(default="nl-query-agent", description="LangSmith project.")


class GraphSettings(BaseSettings):
    """Graph execution control settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GRAPH_",
        case_sensitive=False,
        extra="ignore",
    )

    max_iterations: int = Field(
        default=15,
        description="Maximum agent-tool cycles to prevent infinite loops.",
    )


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://dvdrental:dvdrental@localhost:5433/dvdrental",
        validation_alias="DATABASE_URL",
        description="PostgreSQL connection URL for the DVD Rental database.",
    )
    metadata_schema: str = Field(
        default="agent_metadata",
        validation_alias="METADATA_SCHEMA",
        description="PostgreSQL schema for agent metadata tables.",
    )


class ApplicationSettings(BaseSettings):
    """HTTP API application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    api_host: str = Field(default="0.0.0.0", description="FastAPI host.")
    api_port: int = Field(default=8000, description="FastAPI port.")
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production).",
    )


class SQLSafetySettings(BaseSettings):
    """SQL execution safety limits."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SQL_",
        case_sensitive=False,
        extra="ignore",
    )

    max_rows: int = Field(default=100, description="Maximum rows returned per query.")
    timeout_seconds: int = Field(
        default=30, description="Query execution timeout in seconds."
    )


class StreamlitSettings(BaseSettings):
    """Streamlit UI settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    streamlit_port: int = Field(
        default=8501,
        validation_alias="STREAMLIT_PORT",
        description="Streamlit server port.",
    )
    api_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="API_BASE_URL",
        description="FastAPI backend URL for the UI to call.",
    )


class Settings:
    """Top-level settings composing all sub-settings."""

    def __init__(self) -> None:
        self.llm = LLMSettings()
        self.langsmith = LangSmithSettings()
        self.graph = GraphSettings()
        self.db = DatabaseSettings()
        self.app = ApplicationSettings()
        self.sql = SQLSafetySettings()
        self.ui = StreamlitSettings()


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
