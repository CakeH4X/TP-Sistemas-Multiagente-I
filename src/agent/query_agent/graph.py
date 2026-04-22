"""Query Agent graph — Planner/Generator/Critic/Confirm/Executor/Presenter."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agent.query_agent.edges import route_after_confirm, route_after_critic
from agent.query_agent.nodes import (
    error_response,
    query_planner,
    result_presenter,
    sql_confirm,
    sql_critic,
    sql_executor,
    sql_generator,
)
from agent.state import QueryAgentState


def build_query_graph() -> StateGraph:
    graph = StateGraph(QueryAgentState)

    graph.add_node("query_planner", query_planner)
    graph.add_node("sql_generator", sql_generator)
    graph.add_node("sql_critic", sql_critic)
    graph.add_node("sql_confirm", sql_confirm)
    graph.add_node("sql_executor", sql_executor)
    graph.add_node("result_presenter", result_presenter)
    graph.add_node("error_response", error_response)

    graph.set_entry_point("query_planner")

    graph.add_edge("query_planner", "sql_generator")
    graph.add_edge("sql_generator", "sql_critic")
    graph.add_conditional_edges(
        "sql_critic",
        route_after_critic,
        {
            "passed": "sql_confirm",
            "failed": "sql_generator",
            "error": "error_response",
        },
    )
    graph.add_conditional_edges(
        "sql_confirm",
        route_after_confirm,
        {
            "confirmed": "sql_executor",
            "rejected": END,
        },
    )
    graph.add_edge("sql_executor", "result_presenter")
    graph.add_edge("result_presenter", END)
    graph.add_edge("error_response", END)

    return graph


_compiled = None


def get_compiled_query_graph():
    """Return a singleton compiled Query Agent graph.

    HITL is conditional inside the ``sql_confirm`` node via
    ``langgraph.types.interrupt``, so no ``interrupt_before`` is needed here.
    """
    global _compiled
    if _compiled is None:
        _compiled = build_query_graph().compile(checkpointer=MemorySaver())
    return _compiled
