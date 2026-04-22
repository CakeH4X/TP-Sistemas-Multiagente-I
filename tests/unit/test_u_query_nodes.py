"""Unit tests for Query Agent nodes with mocked LLM, MCP, and persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agent.query_agent import nodes as qa_nodes
from agent.query_agent.nodes import (
    _format_schema_descriptions,
    _needs_confirmation,
    _parse_json_object,
    _strip_sql_fences,
    error_response,
    query_planner,
    result_presenter,
    sql_confirm,
    sql_critic,
    sql_executor,
    sql_generator,
)

# --- helpers -------------------------------------------------------------


def _fake_llm(text: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=text)
    return llm


def _patch_llm(text: str):
    """Patch ``LLMClient`` so ``.as_model().invoke()`` returns ``text``."""
    return patch.object(
        qa_nodes,
        "LLMClient",
        return_value=MagicMock(as_model=lambda: _fake_llm(text)),
    )


# --- pure helpers --------------------------------------------------------


def test_format_schema_descriptions_renders_table_and_columns():
    out = _format_schema_descriptions(
        {"film": {"__table__": "Films catalog.", "title": "Film name."}}
    )
    assert "Table film: Films catalog." in out
    assert "title: Film name." in out


def test_format_schema_descriptions_handles_empty():
    assert "no descriptions" in _format_schema_descriptions({})


def test_strip_sql_fences_removes_markdown():
    assert _strip_sql_fences("```sql\nSELECT 1\n```") == "SELECT 1"


def test_strip_sql_fences_drops_trailing_semicolon():
    assert _strip_sql_fences("SELECT 1;") == "SELECT 1"


def test_parse_json_object_handles_fences_and_prose():
    assert _parse_json_object('Here:\n{"a": 1}\nbye') == {"a": 1}


# --- _needs_confirmation -------------------------------------------------


def test_needs_confirmation_true_when_no_limit():
    assert _needs_confirmation("SELECT id FROM film", {}) is True


def test_needs_confirmation_false_for_simple_limited_select():
    assert _needs_confirmation("SELECT id FROM film LIMIT 10", {}) is False


def test_needs_confirmation_true_when_user_pref_enabled():
    assert (
        _needs_confirmation(
            "SELECT id FROM film LIMIT 10", {"confirm_before_execute": True}
        )
        is True
    )


def test_needs_confirmation_true_for_4_plus_table_joins():
    sql = (
        "SELECT 1 FROM film f "
        "JOIN film_actor fa ON fa.film_id = f.film_id "
        "JOIN actor a ON a.actor_id = fa.actor_id "
        "JOIN language l ON l.language_id = f.language_id "
        "LIMIT 10"
    )
    assert _needs_confirmation(sql, {}) is True


# --- query_planner -------------------------------------------------------


def test_query_planner_loads_descriptions_and_calls_llm():
    state = {
        "messages": [HumanMessage(content="how many films?")],
        "user_preferences": {"language": "en", "date_format": "YYYY-MM-DD"},
        "iteration": 0,
    }
    with (
        patch.object(qa_nodes, "PersistentMemory") as mock_pm,
        _patch_llm("1. join film and language\n2. count rows"),
    ):
        mock_pm.return_value.get_schema_descriptions.return_value = {
            "film": {"__table__": "films"}
        }
        result = query_planner(state)

    mock_pm.return_value.get_schema_descriptions.assert_called_once()
    assert "join" in result["query_plan"].lower()


def test_query_planner_includes_followup_hint_when_session_has_last_sql():
    state = {
        "messages": [HumanMessage(content="now filter by 2006")],
        "user_preferences": {"language": "en", "date_format": "YYYY-MM-DD"},
        "session_context": {
            "last_sql": "SELECT title FROM film",
            "last_query_plan": "list films",
            "last_result_summary": "1000 row(s) returned",
        },
        "iteration": 0,
    }
    captured: dict = {}

    def capture(msgs):
        captured["system"] = msgs[0].content
        return MagicMock(content="plan")

    llm = MagicMock()
    llm.invoke.side_effect = capture
    with (
        patch.object(qa_nodes, "PersistentMemory") as mock_pm,
        patch.object(qa_nodes, "LLMClient") as mock_client,
    ):
        mock_pm.return_value.get_schema_descriptions.return_value = {}
        mock_client.return_value.as_model.return_value = llm
        query_planner(state)

    assert "previous" in captured["system"].lower()
    assert "SELECT title FROM film" in captured["system"]


# --- sql_generator -------------------------------------------------------


def test_sql_generator_strips_markdown_and_increments_iteration():
    state = {
        "messages": [HumanMessage(content="how many films?")],
        "query_plan": "count films",
        "user_preferences": {"max_results": 50, "date_format": "YYYY-MM-DD"},
        "iteration": 0,
    }
    with _patch_llm("```sql\nSELECT COUNT(*) FROM film LIMIT 50;\n```"):
        result = sql_generator(state)

    assert result["generated_sql"] == "SELECT COUNT(*) FROM film LIMIT 50"
    assert result["iteration"] == 1


def test_sql_generator_includes_critic_feedback_on_retry():
    state = {
        "messages": [HumanMessage(content="q")],
        "query_plan": "p",
        "user_preferences": {},
        "iteration": 1,
        "sql_validation": {
            "status": "failed",
            "issues": ["Unknown table x"],
            "suggestions": ["Use only public tables"],
        },
    }
    captured: dict = {}

    def capture(msgs):
        captured["user"] = msgs[1].content
        return MagicMock(content="SELECT 1 FROM film LIMIT 1")

    llm = MagicMock()
    llm.invoke.side_effect = capture
    with patch.object(qa_nodes, "LLMClient") as mock_client:
        mock_client.return_value.as_model.return_value = llm
        sql_generator(state)

    assert "Unknown table x" in captured["user"]
    assert "public tables" in captured["user"]


# --- sql_critic ----------------------------------------------------------


def test_sql_critic_passes_when_safe_schema_and_semantic_ok():
    state = {
        "generated_sql": "SELECT title FROM film LIMIT 5",
        "messages": [HumanMessage(content="list films")],
    }
    with (
        patch.object(qa_nodes, "_existing_tables", return_value={"film"}),
        _patch_llm('{"answers_question": true, "reason": "ok"}'),
    ):
        result = sql_critic(state)
    assert result["sql_validation"]["status"] == "passed"
    assert result["sql_validation"]["issues"] == []


def test_sql_critic_fails_on_unsafe_sql():
    state = {
        "generated_sql": "DELETE FROM film",
        "messages": [HumanMessage(content="x")],
    }
    result = sql_critic(state)
    assert result["sql_validation"]["status"] == "failed"
    assert any(
        "must start with SELECT" in i or "forbidden write" in i
        for i in result["sql_validation"]["issues"]
    )


def test_sql_critic_fails_on_unknown_table():
    state = {
        "generated_sql": "SELECT 1 FROM nonexistent LIMIT 1",
        "messages": [HumanMessage(content="x")],
    }
    with patch.object(qa_nodes, "_existing_tables", return_value={"film"}):
        result = sql_critic(state)
    assert result["sql_validation"]["status"] == "failed"
    assert any("Unknown tables" in i for i in result["sql_validation"]["issues"])


def test_sql_critic_semantic_concern_becomes_advisory_suggestion():
    """Semantic verdict is advisory: passes structurally, surfaces as suggestion."""
    state = {
        "generated_sql": "SELECT 1 FROM film LIMIT 1",
        "messages": [HumanMessage(content="how many actors?")],
    }
    with (
        patch.object(qa_nodes, "_existing_tables", return_value={"film"}),
        _patch_llm('{"answers_question": false, "reason": "wrong table"}'),
    ):
        result = sql_critic(state)

    assert result["sql_validation"]["status"] == "passed"
    assert any("Semantic concern" in s for s in result["sql_validation"]["suggestions"])


# --- sql_confirm ----------------------------------------------------------


def test_sql_confirm_auto_approves_when_low_risk():
    state = {
        "generated_sql": "SELECT title FROM film LIMIT 10",
        "user_preferences": {"confirm_before_execute": False},
    }
    result = sql_confirm(state)
    assert result["sql_approved"] is True
    assert "Auto-approved" in result["messages"][0].content


# --- sql_executor --------------------------------------------------------


def test_sql_executor_calls_mcp_and_returns_result():
    state = {
        "generated_sql": "SELECT 1",
        "user_preferences": {"max_results": 10},
    }
    fake_result = {"columns": ["a"], "rows": [{"a": 1}], "row_count": 1}
    with patch.object(qa_nodes, "mcp_execute_sql", return_value=fake_result) as mexec:
        result = sql_executor(state)
    mexec.assert_called_once()
    assert result["query_result"] == fake_result


def test_sql_executor_captures_errors_into_state():
    state = {"generated_sql": "SELECT 1", "user_preferences": {}}
    with patch.object(
        qa_nodes, "mcp_execute_sql", side_effect=RuntimeError("db blew up")
    ):
        result = sql_executor(state)
    assert "db blew up" in result["error"]


# --- result_presenter ----------------------------------------------------


def test_result_presenter_formats_response_and_updates_short_term_memory():
    state = {
        "messages": [HumanMessage(content="how many films?")],
        "session_id": "s1",
        "generated_sql": "SELECT COUNT(*) FROM film",
        "query_result": {"columns": ["c"], "rows": [{"c": 1000}], "row_count": 1},
        "query_plan": "count films",
        "user_preferences": {"language": "en", "date_format": "YYYY-MM-DD"},
    }
    fake_mem = MagicMock()

    with (
        _patch_llm("There are 1000 films."),
        patch.object(qa_nodes, "get_short_term_memory", return_value=fake_mem),
    ):
        result = result_presenter(state)

    assert "1000" in result["formatted_response"]
    assert isinstance(result["messages"][0], AIMessage)

    fake_mem.set_context.assert_any_call("s1", "last_sql", "SELECT COUNT(*) FROM film")
    fake_mem.set_context.assert_any_call(
        "s1", "last_result_summary", "1 row(s) returned"
    )
    assert fake_mem.add_message.call_count == 2  # user + assistant


# --- error_response ------------------------------------------------------


def test_error_response_uses_critic_issues_when_present():
    state = {
        "sql_validation": {
            "status": "failed",
            "issues": ["unknown table foo"],
            "suggestions": [],
        }
    }
    result = error_response(state)
    assert "unknown table foo" in result["formatted_response"]


def test_error_response_uses_state_error_otherwise():
    result = error_response({"error": "connection refused"})
    assert "connection refused" in result["formatted_response"]
