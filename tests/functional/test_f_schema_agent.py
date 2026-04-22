"""Functional tests for the real Schema Agent (Phase 4).

Hits the real DB and real LLM (via LiteLLM proxy). Requires ``LLM_API_KEY``
to be set and the DVD Rental Postgres to be running. Each approve test
cleans up its persisted descriptions so re-runs are idempotent.
"""

from __future__ import annotations

import os

import psycopg
import pytest

import config.settings as settings_module

needs_llm = pytest.mark.skipif(
    not os.environ.get("LLM_API_KEY"),
    reason="LLM_API_KEY not set — skipping tests that hit the LLM",
)


EXPECTED_DVDRENTAL_TABLES = {
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
def cleanup_descriptions():
    """Delete any descriptions persisted by the test user."""
    yield
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by IN (%s)",
            ("phase4-test-user",),
        )
        conn.commit()


@needs_llm
def test_schema_analyze_initial_request_describes_all_dvdrental_tables(test_client):
    response = test_client.post(
        "/schema/analyze",
        json={"session_id": "sF1", "user_id": "phase4-test-user"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_review"

    generated = body["review_data"]["generated_descriptions"]
    assert set(generated.keys()) == EXPECTED_DVDRENTAL_TABLES

    # Each table has at least a __table__ description, and it's non-empty real text
    # (not our stub "(failed to generate ...)" sentinel).
    film_desc = generated["film"]["__table__"]
    assert film_desc and "(failed to generate" not in film_desc


@needs_llm
def test_schema_analyze_approve_persists_descriptions(
    test_client, cleanup_descriptions
):
    start = test_client.post(
        "/schema/analyze",
        json={"session_id": "sF2", "user_id": "phase4-test-user"},
    ).json()

    resume = test_client.post(
        "/schema/analyze",
        json={
            "session_id": "sF2",
            "user_id": "phase4-test-user",
            "thread_id": start["thread_id"],
            "message": "approve",
        },
    )
    assert resume.status_code == 200
    assert resume.json()["status"] == "completed"

    # Verify they made it to Postgres
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(DISTINCT table_name) "
            f"FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by = %s",
            ("phase4-test-user",),
        )
        (distinct_tables,) = cur.fetchone()
    assert distinct_tables == len(EXPECTED_DVDRENTAL_TABLES)


@needs_llm
def test_schema_analyze_reject_does_not_persist(test_client, cleanup_descriptions):
    start = test_client.post(
        "/schema/analyze",
        json={"session_id": "sF3", "user_id": "phase4-test-user"},
    ).json()

    resume = test_client.post(
        "/schema/analyze",
        json={
            "session_id": "sF3",
            "user_id": "phase4-test-user",
            "thread_id": start["thread_id"],
            "message": "reject",
        },
    )
    assert resume.status_code == 200
    assert resume.json()["status"] == "completed"

    # Nothing persisted under this user
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {settings.db.metadata_schema}.schema_descriptions "
            "WHERE approved_by = %s",
            ("phase4-test-user",),
        )
        (count,) = cur.fetchone()
    assert count == 0
