"""POST /chat — Query Agent endpoint with conditional HITL resume support."""

from __future__ import annotations

import dataclasses
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage
from langgraph.types import Command
from pydantic import BaseModel

from agent.query_agent.graph import get_compiled_query_graph
from agent.state import initial_query_state
from config.settings import get_settings
from memory import get_short_term_memory
from memory.persistent import PersistentMemory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    status: str
    message: str | None = None
    sql: str | None = None
    data: dict | None = None
    thread_id: str
    review_data: dict | None = None
    prompt: str | None = None


def _last_ai_text(state: dict) -> str | None:
    for m in reversed(state.get("messages", []) or []):
        if isinstance(m, AIMessage):
            return str(m.content)
    return None


def _interrupt_payload(result: dict, snapshot) -> dict | None:
    """Return the active interrupt payload, if any.

    Checks the invocation result first (``__interrupt__`` key surfaces the
    interrupt directly when ``langgraph.types.interrupt`` is called), then
    falls back to scanning the checkpoint snapshot's pending tasks.
    """
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if interrupts:
        value = interrupts[-1].value
        return value if isinstance(value, dict) else {"value": value}

    for task in getattr(snapshot, "tasks", ()) or ():
        task_interrupts = getattr(task, "interrupts", None) or ()
        if task_interrupts:
            value = task_interrupts[-1].value
            return value if isinstance(value, dict) else {"value": value}
    return None


def _session_context_dict(session_id: str) -> dict[str, Any]:
    ctx = get_short_term_memory().get_session(session_id)
    return {k: v for k, v in dataclasses.asdict(ctx).items() if k != "extra"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    graph = get_compiled_query_graph()
    settings = get_settings()

    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if request.thread_id is None:
            # Fresh — load user prefs + session context, build initial state.
            preferences = PersistentMemory().get_user_preferences(request.user_id)
            session_context = _session_context_dict(request.session_id)

            state = initial_query_state(
                message=request.message,
                session_id=request.session_id,
                user_id=request.user_id,
                preferences=preferences,
                session_context=session_context,
            )
            state["max_iterations"] = settings.graph.max_iterations

            result: dict[str, Any] = graph.invoke(state, config=config)
        else:
            # Resume — pass the user's reply through the interrupt() return value.
            result = graph.invoke(Command(resume=request.message), config=config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Query graph failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    snapshot = graph.get_state(config)
    payload = _interrupt_payload(result, snapshot)
    if payload is not None:
        return ChatResponse(
            status="pending_review",
            thread_id=thread_id,
            review_data={"sql": payload.get("sql") or result.get("generated_sql")},
            prompt=payload.get("prompt") or "Reply with 'approve' or 'reject'.",
        )

    return ChatResponse(
        status="completed",
        message=_last_ai_text(result) or result.get("formatted_response"),
        sql=result.get("generated_sql"),
        data=result.get("query_result"),
        thread_id=thread_id,
    )
