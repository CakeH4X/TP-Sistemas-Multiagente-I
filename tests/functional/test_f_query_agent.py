"""Functional tests for the real Query Agent (Phase 5).

Hits the real DB, real LLM (LiteLLM proxy), and real persistent + short-term
memory. Requires ``LLM_API_KEY`` and a running DVD Rental Postgres.

For low-risk SQL (single table + LIMIT), the conditional HITL auto-approves
and the response comes back as ``completed`` in one round-trip. For
higher-risk SQL (multi-table joins or no LIMIT), the agent pauses for
``pending_review`` first, just like the Schema Agent.
"""

from __future__ import annotations

import os

import pytest

import config.settings as settings_module

needs_llm = pytest.mark.skipif(
    not os.environ.get("LLM_API_KEY")
    or os.environ.get("LLM_API_KEY", "").startswith("sk-..."),
    reason="LLM_API_KEY not set — skipping tests that hit the LLM",
)


@pytest.fixture(autouse=True)
def _reset_settings():
    settings_module._settings = None
    yield
    settings_module._settings = None


@needs_llm
def test_chat_simple_count_returns_completed_with_data(test_client):
    """A simple count question should reach completion with the right answer.

    Whether HITL is auto-bypassed depends on whether the LLM emits a LIMIT
    clause for the COUNT (per spec §8.5, "no LIMIT" triggers confirmation).
    Test handles both paths.
    """
    body = test_client.post(
        "/chat",
        json={
            "session_id": "qf-1",
            "user_id": "phase5-test-user",
            "message": "How many films are in the database?",
        },
    ).json()

    if body["status"] == "pending_review":
        body = test_client.post(
            "/chat",
            json={
                "session_id": "qf-1",
                "user_id": "phase5-test-user",
                "thread_id": body["thread_id"],
                "message": "approve",
            },
        ).json()

    assert body["status"] == "completed", body
    assert body["sql"] and "film" in body["sql"].lower()
    assert body["data"] is not None
    assert body["data"]["row_count"] >= 1
    # Accept "1000", "1,000", "1.000", etc.
    assert "1000" in body["message"].replace(",", "").replace(".", "")


@needs_llm
def test_chat_complex_query_pauses_for_hitl_then_completes_on_approve(test_client):
    """A 4+ table join should trigger HITL confirmation."""
    start = test_client.post(
        "/chat",
        json={
            "session_id": "qf-2",
            "user_id": "phase5-test-user",
            "message": (
                "Show the title of each film, the actor's first and last name, "
                "the language name, and the category name, limited to 10 rows."
            ),
        },
    ).json()

    # Should pause for review since this needs joins across 4+ tables.
    assert start["status"] == "pending_review", start
    assert start["review_data"]["sql"]

    resume = test_client.post(
        "/chat",
        json={
            "session_id": "qf-2",
            "user_id": "phase5-test-user",
            "thread_id": start["thread_id"],
            "message": "approve",
        },
    ).json()

    assert resume["status"] == "completed", resume
    assert resume["data"]["row_count"] >= 1


@needs_llm
def test_chat_reject_after_hitl_returns_no_data(test_client):
    start = test_client.post(
        "/chat",
        json={
            "session_id": "qf-3",
            "user_id": "phase5-test-user",
            "message": ("Show every film, actor, and category combination — no limit."),
        },
    ).json()
    assert start["status"] == "pending_review"

    resume = test_client.post(
        "/chat",
        json={
            "session_id": "qf-3",
            "user_id": "phase5-test-user",
            "thread_id": start["thread_id"],
            "message": "reject",
        },
    ).json()

    assert resume["status"] == "completed"
    assert resume["data"] is None


def _ask_until_complete(client, session_id: str, user_id: str, message: str) -> dict:
    """Helper: ask a question and auto-approve any HITL pause."""
    body = client.post(
        "/chat",
        json={"session_id": session_id, "user_id": user_id, "message": message},
    ).json()
    if body.get("status") == "pending_review":
        body = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "user_id": user_id,
                "thread_id": body["thread_id"],
                "message": "approve",
            },
        ).json()
    return body


@needs_llm
def test_chat_followup_uses_session_context(test_client):
    """Second question in the same session should leverage prior result."""
    first = _ask_until_complete(
        test_client, "qf-4", "phase5-test-user", "How many films are PG rated?"
    )
    assert first["status"] == "completed", first
    assert first["sql"]

    follow = _ask_until_complete(
        test_client, "qf-4", "phase5-test-user", "What about R rated?"
    )
    assert follow["status"] == "completed", follow
    assert follow["sql"] and "rating" in follow["sql"].lower()
