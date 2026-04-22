"""Integration tests: execute the 3 demo NL queries from spec §20.

Scenarios 2–5 are the query-focused demos. Each tests real LLM + real DB.
"""

from __future__ import annotations

import os
import uuid

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
def test_scenario2_simple_count(test_client):
    """Spec §20 Scenario 2: 'How many films are in the database?'"""
    r = _ask(
        test_client,
        str(uuid.uuid4()),
        "demo-user",
        "How many films are in the database?",
    )
    assert r["status"] == "completed"
    assert r["data"]["row_count"] >= 1
    assert "1000" in r["message"].replace(",", "").replace(".", "")


@needs_llm
def test_scenario3_top_rented_films(test_client):
    """Spec §20 Scenario 3: 'What are the top 5 most rented films?'"""
    r = _ask(
        test_client,
        str(uuid.uuid4()),
        "demo-user",
        "What are the top 5 most rented films?",
    )
    assert r["status"] == "completed"
    assert r["data"]["row_count"] >= 1
    assert r["data"]["row_count"] <= 10
    # SQL should reference rental + film tables
    sql_lower = r["sql"].lower()
    assert "rental" in sql_lower or "rent" in sql_lower
    assert "film" in sql_lower


@needs_llm
def test_scenario4_followup_refinement(test_client):
    """Spec §20 Scenario 4: follow-up 'Filter those by the Action category only'."""
    sid = str(uuid.uuid4())

    first = _ask(test_client, sid, "demo-user", "What are the top 5 most rented films?")
    assert first["status"] == "completed"

    follow = _ask(
        test_client, sid, "demo-user", "Filter those by the Action category only"
    )
    assert follow["status"] == "completed"
    sql_lower = follow["sql"].lower()
    assert "category" in sql_lower or "action" in sql_lower


@needs_llm
def test_scenario5_revenue_per_month(test_client):
    """Spec §20 Scenario 5 (adapted: DVD Rental data is from 2007)."""
    r = _ask(
        test_client,
        str(uuid.uuid4()),
        "demo-user",
        "What was the total revenue per month in 2007?",
    )
    assert r["status"] == "completed"
    assert r["data"] is not None, f"No data returned. Message: {r.get('message')}"
    assert r["data"]["row_count"] >= 1
    sql_lower = r["sql"].lower()
    assert "payment" in sql_lower
    assert "2005" in sql_lower or "extract" in sql_lower
