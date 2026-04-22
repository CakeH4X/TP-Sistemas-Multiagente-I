import os

from dotenv import load_dotenv

# Load .env so LLM_API_KEY etc. are available to tests without `source .env`.
load_dotenv()

os.environ["ENVIRONMENT"] = "test"

# Tests run on the host, so the Docker-network hostname in .env (``postgres:5432``)
# is not resolvable. Rewrite it to the forwarded host port for test runs.
_db = os.environ.get("DATABASE_URL", "")
if not _db or "@postgres:" in _db:
    os.environ["DATABASE_URL"] = (
        "postgresql://dvdrental:dvdrental@localhost:5433/dvdrental"
    )

os.environ.setdefault("LLM_SERVICE_URL", "https://sa-llmproxy.it.itba.edu.ar")
os.environ.setdefault("LLM_MODEL", "gpt-4.1-mini")

import pytest  # noqa: E402


@pytest.fixture
def test_client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)
