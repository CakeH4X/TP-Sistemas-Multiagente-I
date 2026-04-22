"""Application logging configuration."""

import logging

from config.settings import get_settings


def configure_logging() -> None:
    """Configure root logging based on application settings."""
    settings = get_settings()
    env_log_levels = {
        "development": logging.DEBUG,
        "test": logging.DEBUG,
        "staging": logging.INFO,
        "production": logging.WARNING,
    }
    level = env_log_levels.get(settings.app.environment, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
