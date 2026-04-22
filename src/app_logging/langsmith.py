"""LangSmith tracing configuration helpers."""

import logging
import os
import warnings

from config.settings import get_settings

logger = logging.getLogger(__name__)


def configure_langsmith() -> None:
    """Configure LangSmith / LangChain tracing environment variables."""
    settings = get_settings()

    warnings.filterwarnings(
        "ignore",
        message=".*LangSmith.*",
        category=UserWarning,
    )

    if settings.langsmith.tracing and settings.langsmith.api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith.endpoint
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith.api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith.project
        logger.info(
            "LangSmith tracing enabled (project=%s)",
            settings.langsmith.project,
        )
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        if not settings.langsmith.tracing:
            logger.debug("LangSmith disabled: LANGSMITH_TRACING is not true")
        else:
            logger.debug("LangSmith disabled: LANGSMITH_API_KEY not set")
