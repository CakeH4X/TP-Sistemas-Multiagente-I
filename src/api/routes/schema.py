"""POST /schema/analyze — Schema Agent endpoint with HITL resume support.

Also exposes GET /schema/descriptions for reading approved descriptions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from agent.schema_agent.graph import get_compiled_schema_graph
from agent.state import initial_schema_state
from memory.persistent import PersistentMemory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["schema"])


class SchemaAnalyzeRequest(BaseModel):
    session_id: str
    user_id: str
    thread_id: str | None = None
    message: str | None = None


class SchemaAnalyzeResponse(BaseModel):
    status: str
    thread_id: str
    message: str | None = None
    review_data: dict | None = None
    prompt: str | None = None


def _last_ai_text(state: dict) -> str | None:
    for m in reversed(state.get("messages", []) or []):
        if isinstance(m, AIMessage):
            return str(m.content)
    return None


@router.post("/schema/analyze", response_model=SchemaAnalyzeResponse)
async def schema_analyze(request: SchemaAnalyzeRequest) -> SchemaAnalyzeResponse:
    graph = get_compiled_schema_graph()

    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if request.thread_id is None:
            state = initial_schema_state(
                message=request.message or "Analyze the full database schema.",
                session_id=request.session_id,
                user_id=request.user_id,
            )
            result: dict[str, Any] = graph.invoke(state, config=config)
        else:
            graph.update_state(
                config,
                {"messages": [HumanMessage(content=request.message or "")]},
            )
            result = graph.invoke(None, config=config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Schema graph failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    snapshot = graph.get_state(config)
    if snapshot.next:
        return SchemaAnalyzeResponse(
            status="pending_review",
            thread_id=thread_id,
            review_data={
                "generated_descriptions": result.get("generated_descriptions", {})
            },
            prompt="Review the descriptions. Reply 'approve' or provide revisions.",
        )

    return SchemaAnalyzeResponse(
        status="completed",
        thread_id=thread_id,
        message=_last_ai_text(result),
    )


@router.get("/schema/descriptions")
async def get_schema_descriptions(table_name: str | None = None) -> dict:
    store = PersistentMemory()
    return store.get_schema_descriptions(table_name)
