FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/
RUN uv sync --frozen --no-dev

COPY src /app/src

ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

FROM base AS production

CMD ["uv", "run", "uvicorn", "api.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
