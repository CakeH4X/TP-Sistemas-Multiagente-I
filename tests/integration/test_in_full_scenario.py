"""Full E2E integration test: set preferences → document schema → query → follow-up.

Requires running PostgreSQL + LLM proxy.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

import config.settings as settings_module

needs_llm = pytest.mark.skipif(
    not os.environ.get("LLM_API_KEY")
    or os.environ.get("LLM_API_KEY", "").startswith("sk-..."),
    reason="LLM_API_KEY not set",
)


@pytest.fixture(autouse=True)
def _reset_settings():
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture
def user_id():
    return f"int-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup(user_id):
    yield
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {settings.db.metadata_schema}.user_preferences "
            "WHERE user_id = %s",
            (user_id,),
        )
        cur.execute(
            f"DELETE FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by = %s",
            (user_id,),
        )
        conn.commit()


def _ask(client, session_id, user_id, message, thread_id=None):
    """Ask a question, auto-approving any HITL pause."""
    r = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            **({"thread_id": thread_id} if thread_id else {}),
        },
    ).json()
    if r.get("status") == "pending_review":
        r = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "user_id": user_id,
                "message": "approve",
                "thread_id": r["thread_id"],
            },
        ).json()
    return r


@needs_llm
def test_full_scenario(test_client, user_id, cleanup):
    # --- 1. Set preferences -----------------------------------------------
    prefs_resp = test_client.put(
        f"/preferences/{user_id}",
        json={"preferences": {"language": "en", "max_results": 10}},
    )
    assert prefs_resp.status_code == 200
    saved = prefs_resp.json()["preferences"]
    assert saved["language"] == "en"
    assert saved["max_results"] == 10

    # --- 2. Schema documentation ------------------------------------------
    sid = str(uuid.uuid4())
    schema_start = test_client.post(
        "/schema/analyze",
        json={"session_id": sid, "user_id": user_id},
    ).json()
    assert schema_start["status"] == "pending_review"
    descs = schema_start["review_data"]["generated_descriptions"]
    assert len(descs) >= 15

    schema_done = test_client.post(
        "/schema/analyze",
        json={
            "session_id": sid,
            "user_id": user_id,
            "thread_id": schema_start["thread_id"],
            "message": "approve",
        },
    ).json()
    assert schema_done["status"] == "completed"

    # Verify descriptions persisted
    persisted = test_client.get("/schema/descriptions").json()
    assert len(persisted) >= 15

    # --- 3. Query ---------------------------------------------------------
    chat_sid = str(uuid.uuid4())
    r1 = _ask(test_client, chat_sid, user_id, "How many films are in the database?")
    assert r1["status"] == "completed"
    assert r1["data"]["row_count"] >= 1

    # --- 4. Follow-up ----------------------------------------------------
    r2 = _ask(test_client, chat_sid, user_id, "What about PG rated films?")
    assert r2["status"] == "completed"
    assert r2["sql"] and "rating" in r2["sql"].lower()
