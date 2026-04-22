"""Agent state definitions for both Schema and Query agents."""

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class BaseAgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    user_id: str
    user_preferences: dict
    session_context: dict
    iteration: int
    max_iterations: int
    error: str | None


class SchemaAgentState(BaseAgentState, total=False):
    target_tables: list[str]
    schema_info: dict
    generated_descriptions: dict
    approved_descriptions: dict
    schema_review_status: str  # "pending" | "approved" | "rejected" | "revised"


class QueryAgentState(BaseAgentState, total=False):
    query_plan: str
    generated_sql: str
    sql_validation: dict
    sql_approved: bool
    query_result: dict
    formatted_response: str


def initial_schema_state(
    message: str,
    session_id: str,
    user_id: str,
    preferences: dict | None = None,
) -> SchemaAgentState:
    from langchain_core.messages import HumanMessage

    return SchemaAgentState(
        messages=[HumanMessage(content=message)],
        session_id=session_id,
        user_id=user_id,
        user_preferences=preferences or {},
        session_context={},
        iteration=0,
    )


def initial_query_state(
    message: str,
    session_id: str,
    user_id: str,
    preferences: dict | None = None,
    session_context: dict | None = None,
) -> QueryAgentState:
    from langchain_core.messages import HumanMessage

    return QueryAgentState(
        messages=[HumanMessage(content=message)],
        session_id=session_id,
        user_id=user_id,
        user_preferences=preferences or {},
        session_context=session_context or {},
        iteration=0,
    )
