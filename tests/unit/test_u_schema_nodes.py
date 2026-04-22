"""Unit tests for Schema Agent nodes with mocked MCP + LLM + persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.schema_agent import nodes as sa_nodes
from agent.schema_agent.nodes import (
    _parse_json_response,
    _topo_sort_by_fk,
    schema_analyzer,
    schema_persister,
    schema_planner,
    schema_review,
)

# --- _topo_sort_by_fk -----------------------------------------------------


def test_topo_sort_leaf_tables_come_first():
    tables = ["film", "language", "film_actor", "actor"]
    fk = {
        "film": {"language"},
        "film_actor": {"film", "actor"},
        "language": set(),
        "actor": set(),
    }
    ordered = _topo_sort_by_fk(tables, fk)

    # Referenced tables (language, actor) before their referrers
    assert ordered.index("language") < ordered.index("film")
    assert ordered.index("film") < ordered.index("film_actor")
    assert ordered.index("actor") < ordered.index("film_actor")


def test_topo_sort_handles_cycles_deterministically():
    # Cycle a -> b -> a; sort should still terminate.
    ordered = _topo_sort_by_fk(["a", "b"], {"a": {"b"}, "b": {"a"}})
    assert sorted(ordered) == ["a", "b"]


def test_topo_sort_empty_input_returns_empty():
    assert _topo_sort_by_fk([], {}) == []


# --- _parse_json_response --------------------------------------------------


def test_parse_json_response_plain():
    data = _parse_json_response('{"__table__": "x", "id": "y"}')
    assert data == {"__table__": "x", "id": "y"}


def test_parse_json_response_with_markdown_fence():
    raw = '```json\n{"__table__": "hi"}\n```'
    data = _parse_json_response(raw)
    assert data == {"__table__": "hi"}


def test_parse_json_response_embedded_in_prose():
    raw = 'Here you go:\n{"__table__": "hello"}\nThanks.'
    data = _parse_json_response(raw)
    assert data == {"__table__": "hello"}


def test_parse_json_response_rejects_non_object():
    with pytest.raises(ValueError):
        _parse_json_response("[1, 2, 3]")


# --- schema_planner -------------------------------------------------------


def test_schema_planner_discovers_and_orders_tables():
    table_list = {"tables": ["film_actor", "film", "actor"]}
    detail_map = {
        "film_actor": {
            "foreign_keys": [
                {"references_table": "film"},
                {"references_table": "actor"},
            ]
        },
        "film": {"foreign_keys": []},
        "actor": {"foreign_keys": []},
    }

    def fake_inspect(name=None):
        return table_list if name is None else detail_map[name]

    with patch.object(sa_nodes, "inspect_schema", side_effect=fake_inspect):
        result = schema_planner({})

    assert result["target_tables"].index("film_actor") > result["target_tables"].index(
        "film"
    )
    assert result["target_tables"].index("film_actor") > result["target_tables"].index(
        "actor"
    )
    assert result["iteration"] == 0


# --- schema_analyzer ------------------------------------------------------


def _fake_llm(response_text: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=response_text)
    return llm


def test_schema_analyzer_generates_descriptions_for_each_table():
    state = {"target_tables": ["film", "actor"], "iteration": 0}

    def fake_inspect(name=None):
        return {
            "columns": [{"column_name": "id", "data_type": "int", "is_nullable": "NO"}],
            "foreign_keys": [],
        }

    fake_sample = {"rows": [{"id": 1}]}
    llm_responses = iter(
        [
            '{"__table__": "films", "id": "pk"}',
            '{"__table__": "actors", "id": "pk"}',
        ]
    )

    llm = MagicMock()
    llm.invoke.side_effect = lambda msgs: MagicMock(content=next(llm_responses))

    with (
        patch.object(sa_nodes, "inspect_schema", side_effect=fake_inspect),
        patch.object(sa_nodes, "get_table_sample", return_value=fake_sample),
        patch.object(sa_nodes, "LLMClient") as mock_client,
    ):
        mock_client.return_value.as_model.return_value = llm
        result = schema_analyzer(state)

    assert set(result["generated_descriptions"].keys()) == {"film", "actor"}
    assert result["generated_descriptions"]["film"]["__table__"] == "films"
    assert result["iteration"] == 1
    assert result["schema_review_status"] == "pending"


def test_schema_analyzer_captures_errors_per_table():
    state = {"target_tables": ["broken"], "iteration": 0}

    with (
        patch.object(sa_nodes, "inspect_schema", side_effect=RuntimeError("boom")),
        patch.object(sa_nodes, "LLMClient"),
    ):
        result = schema_analyzer(state)

    assert (
        "failed to generate" in result["generated_descriptions"]["broken"]["__table__"]
    )


def test_schema_analyzer_includes_feedback_on_revised_iteration():
    state = {
        "target_tables": ["film"],
        "iteration": 1,
        "schema_review_status": "revised",
        "messages": [HumanMessage(content="please be more specific")],
    }
    fake_inspect = {"columns": [], "foreign_keys": []}
    fake_sample = {"rows": []}
    llm = _fake_llm('{"__table__": "improved"}')

    with (
        patch.object(sa_nodes, "inspect_schema", return_value=fake_inspect),
        patch.object(sa_nodes, "get_table_sample", return_value=fake_sample),
        patch.object(sa_nodes, "LLMClient") as mock_client,
    ):
        mock_client.return_value.as_model.return_value = llm
        schema_analyzer(state)

    prompt_text = llm.invoke.call_args.args[0][1].content
    assert "please be more specific" in prompt_text


# --- schema_review --------------------------------------------------------


@pytest.mark.parametrize("text", ["approve", "APPROVED", "ok", "yes"])
def test_schema_review_sets_approved_on_affirmative_reply(text):
    state = {
        "messages": [HumanMessage(content=text)],
        "generated_descriptions": {"film": {"__table__": "x"}},
    }
    result = schema_review(state)

    assert result["schema_review_status"] == "approved"
    assert result["approved_descriptions"] == {"film": {"__table__": "x"}}


@pytest.mark.parametrize("text", ["reject", "cancel", "no"])
def test_schema_review_sets_rejected_on_negative_reply(text):
    state = {
        "messages": [HumanMessage(content=text)],
        "generated_descriptions": {"film": {"__table__": "x"}},
    }
    result = schema_review(state)

    assert result["schema_review_status"] == "rejected"
    assert result["approved_descriptions"] == {}


def test_schema_review_sets_revised_on_revision_feedback():
    state = {
        "messages": [HumanMessage(content="please be more concise")],
        "generated_descriptions": {"film": {"__table__": "x"}},
    }
    result = schema_review(state)

    assert result["schema_review_status"] == "revised"


# --- schema_persister -----------------------------------------------------


def test_schema_persister_writes_to_persistent_memory():
    state = {
        "approved_descriptions": {
            "film": {"__table__": "t", "title": "c"},
            "actor": {"__table__": "a"},
        },
        "user_id": "alice",
    }
    with patch.object(sa_nodes, "PersistentMemory") as mock_pm:
        store = mock_pm.return_value
        result = schema_persister(state)

    store.save_schema_descriptions.assert_called_once_with(
        state["approved_descriptions"], approved_by="alice"
    )
    assert isinstance(result["messages"][0], AIMessage)
    assert "Persisted 3" in result["messages"][0].content


def test_schema_persister_surfaces_db_errors():
    state = {"approved_descriptions": {"film": {"__table__": "t"}}, "user_id": "u"}
    with patch.object(sa_nodes, "PersistentMemory") as mock_pm:
        mock_pm.return_value.save_schema_descriptions.side_effect = RuntimeError(
            "db down"
        )
        result = schema_persister(state)

    assert result["error"] == "db down"
    assert "Failed to persist" in result["messages"][0].content
