"""Schema Agent conditional edges."""

from __future__ import annotations

from agent.state import SchemaAgentState

_MAX_REVISION_CYCLES = 3


def route_after_schema_review(state: SchemaAgentState) -> str:
    """Route based on ``schema_review_status`` after the HITL checkpoint."""
    status = state.get("schema_review_status")
    iteration = state.get("iteration", 0)

    if status == "approved":
        return "approved"
    if status == "revised" and iteration < _MAX_REVISION_CYCLES:
        return "revise"
    return "end"
