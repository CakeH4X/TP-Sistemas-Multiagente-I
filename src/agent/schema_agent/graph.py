"""Schema Agent graph (Planner → Analyzer → HITL Review → Persister)."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agent.schema_agent.edges import route_after_schema_review
from agent.schema_agent.nodes import (
    schema_analyzer,
    schema_persister,
    schema_planner,
    schema_review,
)
from agent.state import SchemaAgentState


def build_schema_graph() -> StateGraph:
    graph = StateGraph(SchemaAgentState)

    graph.add_node("schema_planner", schema_planner)
    graph.add_node("schema_analyzer", schema_analyzer)
    graph.add_node("schema_review", schema_review)
    graph.add_node("schema_persister", schema_persister)

    graph.set_entry_point("schema_planner")

    graph.add_edge("schema_planner", "schema_analyzer")
    graph.add_edge("schema_analyzer", "schema_review")
    graph.add_conditional_edges(
        "schema_review",
        route_after_schema_review,
        {
            "approved": "schema_persister",
            "revise": "schema_analyzer",
            "end": END,
        },
    )
    graph.add_edge("schema_persister", END)

    return graph


_compiled = None


def get_compiled_schema_graph():
    """Return a singleton compiled Schema Agent graph with HITL interrupt."""
    global _compiled
    if _compiled is None:
        _compiled = build_schema_graph().compile(
            interrupt_before=["schema_review"],
            checkpointer=MemorySaver(),
        )
    return _compiled
