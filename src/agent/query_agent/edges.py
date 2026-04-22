"""Query Agent conditional edges."""

from __future__ import annotations

from agent.state import QueryAgentState


def route_after_critic(state: QueryAgentState) -> str:
    """Route based on critic status and iteration budget."""
    validation = state.get("sql_validation") or {}
    status = validation.get("status")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 15)

    if status == "passed":
        return "passed"
    if status == "failed" and iteration < max_iter:
        return "failed"
    return "error"


def route_after_confirm(state: QueryAgentState) -> str:
    """Route based on user's HITL decision."""
    return "confirmed" if state.get("sql_approved") else "rejected"
