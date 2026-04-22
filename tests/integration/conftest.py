import os

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

os.environ["ENVIRONMENT"] = "test"

_db = os.environ.get("DATABASE_URL", "")
if not _db or "@postgres:" in _db:
    os.environ["DATABASE_URL"] = (
        "postgresql://dvdrental:dvdrental@localhost:5433/dvdrental"
    )

os.environ.setdefault("LLM_SERVICE_URL", "https://sa-llmproxy.it.itba.edu.ar")
os.environ.setdefault("LLM_MODEL", "gpt-4.1-mini")
