"""Schema Agent nodes — real Phase 4 implementation.

- ``schema_planner``  : discovers all tables via MCP, orders by FK dependency.
- ``schema_analyzer`` : introspects each table + samples rows, asks the LLM
                        to produce human-readable descriptions.
- ``schema_review``   : HITL — inspects the user's resume message.
- ``schema_persister``: writes approved descriptions to Postgres.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.schema_agent.prompts import (
    ANALYZER_SYSTEM_PROMPT,
    build_analyzer_user_prompt,
)
from agent.state import SchemaAgentState
from llm.client import LLMClient
from memory.persistent import PersistentMemory
from tools.mcp_server import get_table_sample, inspect_schema

logger = logging.getLogger(__name__)

_APPROVE_TOKENS = {"approve", "approved", "ok", "yes"}
_REJECT_TOKENS = {"reject", "rejected", "cancel", "no"}


def _topo_sort_by_fk(tables: list[str], fk_map: dict[str, set[str]]) -> list[str]:
    """Return ``tables`` ordered so referenced tables come before referring ones.

    ``fk_map[t]`` is the set of tables that ``t`` references. Leaf tables
    (no outgoing FKs) come first. Cycles are broken deterministically by name.
    """
    remaining = set(tables)
    ordered: list[str] = []
    while remaining:
        leaves = sorted(t for t in remaining if not (fk_map.get(t, set()) & remaining))
        if not leaves:
            # Cycle — drop by name order to keep output deterministic.
            leaves = [sorted(remaining)[0]]
        ordered.extend(leaves)
        remaining.difference_update(leaves)
    return ordered


def schema_planner(state: SchemaAgentState) -> dict:
    """Discover all public tables and order them by FK dependency."""
    logger.info("[PLANNER] schema_planner: discovering tables")
    listing = inspect_schema()
    tables = listing["tables"]

    fk_map: dict[str, set[str]] = {}
    for tbl in tables:
        info = inspect_schema(tbl)
        fk_map[tbl] = {fk["references_table"] for fk in info.get("foreign_keys", [])}

    ordered = _topo_sort_by_fk(tables, fk_map)
    logger.info("[PLANNER] target_tables: %s", ordered)

    return {
        "target_tables": ordered,
        "iteration": state.get("iteration", 0),
        "messages": [
            AIMessage(content=f"Planned documentation for {len(ordered)} tables.")
        ],
    }


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_response(text: str) -> dict[str, str]:
    """Extract a JSON object from an LLM response, tolerating markdown fences."""
    stripped = _JSON_FENCE.sub("", text).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Analyzer response was not a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def _describe_table(
    llm,
    table_name: str,
    revision_feedback: str | None,
) -> dict[str, str]:
    """Call MCP + LLM to produce descriptions for one table."""
    info = inspect_schema(table_name)
    sample = get_table_sample(table_name, limit=5)

    user_prompt = build_analyzer_user_prompt(
        table_name=table_name,
        columns=info["columns"],
        foreign_keys=info.get("foreign_keys", []),
        sample_rows=sample.get("rows", []),
        revision_feedback=revision_feedback,
    )

    response = llm.invoke(
        [
            SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
    )
    return _parse_json_response(str(response.content))


def _last_human_text(state: SchemaAgentState) -> str:
    for m in reversed(state.get("messages", []) or []):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def schema_analyzer(state: SchemaAgentState) -> dict:
    """Generate descriptions for every target table using the LLM + MCP."""
    logger.info("[ANALYZER] schema_analyzer: generating descriptions")

    tables = state.get("target_tables", [])
    iteration = state.get("iteration", 0)

    # On revision cycles, carry the user's feedback into every per-table prompt.
    feedback: str | None = None
    if iteration > 0 and state.get("schema_review_status") == "revised":
        feedback = _last_human_text(state) or None

    llm = LLMClient().as_model()
    generated: dict[str, dict[str, str]] = {}
    for tbl in tables:
        try:
            generated[tbl] = _describe_table(llm, tbl, feedback)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analyzer failed for table %s", tbl)
            generated[tbl] = {"__table__": f"(failed to generate description: {exc})"}

    return {
        "generated_descriptions": generated,
        "iteration": iteration + 1,
        "schema_review_status": "pending",
        "messages": [
            AIMessage(content=f"Generated descriptions for {len(generated)} table(s).")
        ],
    }


def schema_review(state: SchemaAgentState) -> dict:
    """HITL checkpoint — interpret the latest human message.

    Runs after the API resumes the graph via ``invoke(None, config)``.
    """
    logger.info("[REVIEW] schema_review: interpreting user feedback")
    text = _last_human_text(state).strip().lower()
    generated = state.get("generated_descriptions", {})

    if text in _APPROVE_TOKENS:
        status = "approved"
        approved = generated
        reply = "Descriptions approved. Persisting..."
    elif text in _REJECT_TOKENS:
        status = "rejected"
        approved = {}
        reply = "Descriptions rejected. Ending without persisting."
    else:
        status = "revised"
        approved = {}
        reply = "Revising descriptions based on your feedback..."

    return {
        "schema_review_status": status,
        "approved_descriptions": approved,
        "messages": [AIMessage(content=reply)],
    }


def schema_persister(state: SchemaAgentState) -> dict:
    """Upsert approved descriptions into ``agent_metadata.schema_descriptions``."""
    logger.info("[PERSISTER] schema_persister: writing to Postgres")
    approved = state.get("approved_descriptions", {})
    user_id = state.get("user_id") or "unknown"

    try:
        PersistentMemory().save_schema_descriptions(approved, approved_by=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Persister failed")
        return {
            "error": str(exc),
            "messages": [AIMessage(content=f"Failed to persist descriptions: {exc}")],
        }

    count = sum(len(cols) for cols in approved.values())
    return {"messages": [AIMessage(content=f"Persisted {count} description(s).")]}
