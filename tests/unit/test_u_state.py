"""Unit tests for src/agent/state.py and both compiled graphs."""

from langchain_core.messages import HumanMessage

from agent.query_agent.graph import build_query_graph, get_compiled_query_graph
from agent.schema_agent.graph import build_schema_graph, get_compiled_schema_graph
from agent.state import (
    BaseAgentState,
    QueryAgentState,
    SchemaAgentState,
    initial_query_state,
    initial_schema_state,
)

# --- State TypedDict shapes -------------------------------------------------


def test_base_state_accepts_core_keys():
    s: BaseAgentState = {
        "messages": [HumanMessage(content="hi")],
        "session_id": "s1",
        "user_id": "u1",
        "user_preferences": {"language": "en"},
        "session_context": {},
        "iteration": 0,
        "max_iterations": 15,
        "error": None,
    }
    assert s["session_id"] == "s1"


def test_schema_state_has_schema_specific_fields():
    s: SchemaAgentState = {
        "target_tables": ["film"],
        "generated_descriptions": {"film": {"__table__": "x"}},
        "approved_descriptions": {},
        "schema_review_status": "pending",
    }
    assert s["schema_review_status"] == "pending"


def test_query_state_has_query_specific_fields():
    s: QueryAgentState = {
        "query_plan": "plan",
        "generated_sql": "SELECT 1",
        "sql_validation": {"status": "passed"},
        "sql_approved": True,
        "query_result": {"rows": []},
        "formatted_response": "hello",
    }
    assert s["sql_approved"] is True


# --- Factory helpers -------------------------------------------------------


def test_initial_schema_state_populates_required_fields():
    s = initial_schema_state(
        message="analyze", session_id="s1", user_id="u1", preferences={"language": "es"}
    )
    assert s["session_id"] == "s1"
    assert s["user_id"] == "u1"
    assert s["user_preferences"] == {"language": "es"}
    assert s["iteration"] == 0
    assert isinstance(s["messages"][0], HumanMessage)
    assert s["messages"][0].content == "analyze"


def test_initial_query_state_seeds_context_when_absent():
    s = initial_query_state(message="how many films?", session_id="s1", user_id="u1")
    assert s["session_context"] == {}
    assert s["user_preferences"] == {}
    assert s["iteration"] == 0


def test_initial_query_state_preserves_existing_session_context():
    ctx = {"last_sql": "SELECT 1"}
    s = initial_query_state(
        message="follow up", session_id="s1", user_id="u1", session_context=ctx
    )
    assert s["session_context"] == ctx


# --- Graph structure -------------------------------------------------------


def test_schema_graph_has_expected_nodes():
    compiled = get_compiled_schema_graph()
    nodes = set(compiled.get_graph().nodes)
    assert {
        "schema_planner",
        "schema_analyzer",
        "schema_review",
        "schema_persister",
    } <= nodes


def test_query_graph_has_expected_nodes():
    compiled = get_compiled_query_graph()
    nodes = set(compiled.get_graph().nodes)
    assert {
        "query_planner",
        "sql_generator",
        "sql_critic",
        "sql_confirm",
        "sql_executor",
        "result_presenter",
        "error_response",
    } <= nodes


def test_schema_graph_builds_without_compiling():
    # build_schema_graph must succeed on its own (no checkpointer).
    g = build_schema_graph()
    assert g is not None


def test_query_graph_builds_without_compiling():
    g = build_query_graph()
    assert g is not None


# --- End-to-end invocation through the compiled graphs --------------------


def test_schema_graph_invoke_reaches_hitl_interrupt():
    """Fresh invocation should pause at ``schema_review``."""
    graph = get_compiled_schema_graph()
    config = {"configurable": {"thread_id": "test-schema-1"}}

    state = initial_schema_state("analyze", session_id="s1", user_id="u1")
    graph.invoke(state, config=config)

    snapshot = graph.get_state(config)
    assert snapshot.next == ("schema_review",)
    assert snapshot.values.get("generated_descriptions", {}) != {}


def test_schema_graph_resume_approve_reaches_end():
    from langchain_core.messages import HumanMessage

    graph = get_compiled_schema_graph()
    config = {"configurable": {"thread_id": "test-schema-2"}}

    state = initial_schema_state("analyze", session_id="s1", user_id="u1")
    graph.invoke(state, config=config)

    graph.update_state(config, {"messages": [HumanMessage(content="approve")]})
    graph.invoke(None, config=config)

    snapshot = graph.get_state(config)
    assert snapshot.next == ()  # no more nodes — ended


# Phase 5 replaced the Query Agent stubs with real LLM-backed nodes; the
# old stub-era end-to-end assertions live in tests/unit/test_u_query_nodes.py
# (mocked) and tests/functional/test_f_query_agent.py (real LLM + DB).
