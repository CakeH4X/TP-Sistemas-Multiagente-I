"""Integration test: auto-discover full schema, generate descriptions, HITL approve.

Verifies all 15 DVD Rental tables are discovered and described, then
persisted to the agent_metadata schema on approval.
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

EXPECTED_TABLES = {
    "actor",
    "address",
    "category",
    "city",
    "country",
    "customer",
    "film",
    "film_actor",
    "film_category",
    "inventory",
    "language",
    "payment",
    "rental",
    "staff",
    "store",
}


@pytest.fixture(autouse=True)
def _reset_settings():
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture
def user_id():
    return f"int-schema-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup(user_id):
    yield
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by = %s",
            (user_id,),
        )
        conn.commit()


@needs_llm
def test_schema_auto_discover_and_approve(test_client, user_id, cleanup):
    sid = str(uuid.uuid4())

    # Start analysis
    start = test_client.post(
        "/schema/analyze",
        json={"session_id": sid, "user_id": user_id},
    ).json()

    assert start["status"] == "pending_review"
    generated = start["review_data"]["generated_descriptions"]
    assert set(generated.keys()) == EXPECTED_TABLES

    # Each table has at least a __table__ description
    for table, cols in generated.items():
        assert "__table__" in cols, f"{table} missing __table__ description"
        assert cols["__table__"] and "(failed" not in cols["__table__"]

    # Approve
    done = test_client.post(
        "/schema/analyze",
        json={
            "session_id": sid,
            "user_id": user_id,
            "thread_id": start["thread_id"],
            "message": "approve",
        },
    ).json()
    assert done["status"] == "completed"

    # Verify in DB
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT table_name "
            f"FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by = %s",
            (user_id,),
        )
        persisted = {r[0] for r in cur.fetchall()}
    assert persisted == EXPECTED_TABLES


@needs_llm
def test_schema_revision_cycle(test_client, user_id, cleanup):
    """Request a revision before approving — should re-generate."""
    sid = str(uuid.uuid4())

    start = test_client.post(
        "/schema/analyze",
        json={"session_id": sid, "user_id": user_id},
    ).json()
    assert start["status"] == "pending_review"

    # Request revision
    revised = test_client.post(
        "/schema/analyze",
        json={
            "session_id": sid,
            "user_id": user_id,
            "thread_id": start["thread_id"],
            "message": "make all descriptions one sentence maximum",
        },
    ).json()

    # Should pause again for review with new descriptions
    assert revised["status"] == "pending_review"
    assert revised["review_data"]["generated_descriptions"]

    # Approve the revised version
    done = test_client.post(
        "/schema/analyze",
        json={
            "session_id": sid,
            "user_id": user_id,
            "thread_id": revised["thread_id"],
            "message": "approve",
        },
    ).json()
    assert done["status"] == "completed"
