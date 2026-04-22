"""FastAPI application for the NL Query Agent system."""

from dotenv import load_dotenv

load_dotenv()

import logging  # noqa: E402

import psycopg  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.routes.chat import router as chat_router  # noqa: E402
from api.routes.preferences import router as preferences_router  # noqa: E402
from api.routes.schema import router as schema_router  # noqa: E402
from app_logging.langsmith import configure_langsmith  # noqa: E402
from app_logging.logger import configure_logging  # noqa: E402
from config.settings import get_settings  # noqa: E402

settings = get_settings()
configure_logging()
configure_langsmith()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NL Query Agent API",
    description="NL querying over the DVD Rental database via LangGraph agents.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(schema_router)
app.include_router(preferences_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check with database connectivity verification."""
    db_status = "unreachable"
    try:
        with psycopg.connect(settings.db.database_url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        db_status = "connected"
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB health check failed: %s", exc)

    return {
        "status": "healthy",
        "environment": settings.app.environment,
        "database": db_status,
    }


def get_app() -> FastAPI:
    """Application factory used by ASGI servers."""
    return app
