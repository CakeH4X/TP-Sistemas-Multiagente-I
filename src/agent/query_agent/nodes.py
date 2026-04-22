"""Query Agent nodes — real Phase 5 implementation.

Nodes follow Planner → Generator → Critic → (conditional HITL Confirm) →
Executor → Presenter. The Critic feeds back to the Generator on failure
(up to ``max_iterations`` cycles); the Confirm node only interrupts when
the SQL is risky or the user opted into confirmations.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from agent.query_agent.prompts import (
    CRITIC_SEMANTIC_PROMPT,
    GENERATOR_SYSTEM_PROMPT,
    PLANNER_FOLLOWUP_HINT,
    PLANNER_SYSTEM_PROMPT,
    PRESENTER_SYSTEM_PROMPT,
    build_generator_user_prompt,
    build_planner_user_prompt,
    build_presenter_user_prompt,
)
from agent.state import QueryAgentState
from config.settings import get_settings
from llm.client import LLMClient
from memory import get_short_term_memory
from memory.persistent import DEFAULT_PREFERENCES, PersistentMemory
from tools.mcp_server import execute_sql as mcp_execute_sql
from tools.mcp_server import inspect_schema
from tools.sql_safety import validate_sql_safety

logger = logging.getLogger(__name__)

# Match the table portion of FROM/JOIN, allowing optional ``schema.`` prefix
# and quoted identifiers ("foo"."bar").
_FROM_OR_JOIN = re.compile(
    r"""\b(?:FROM|JOIN)\s+
        (?:"?[A-Za-z_][A-Za-z0-9_]*"?\s*\.\s*)?     # optional schema prefix
        "?([A-Za-z_][A-Za-z0-9_]*)"?                # captured table name
    """,
    re.IGNORECASE | re.VERBOSE,
)
_HAS_LIMIT = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def _last_user_text(state: QueryAgentState) -> str:
    for m in reversed(state.get("messages", []) or []):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _format_schema_descriptions(descs: dict[str, dict[str, str]]) -> str:
    """Render persisted descriptions as a compact context block for the LLM."""
    if not descs:
        return "(no descriptions persisted yet)"
    parts: list[str] = []
    for table, cols in sorted(descs.items()):
        table_desc = cols.get("__table__", "")
        parts.append(f"Table {table}: {table_desc}")
        for col, desc in sorted(cols.items()):
            if col != "__table__":
                parts.append(f"  - {col}: {desc}")
    return "\n".join(parts)


def _strip_sql_fences(text: str) -> str:
    cleaned = _CODE_FENCE.sub("", text).strip()
    return cleaned.rstrip(";").strip()


def _parse_json_object(text: str) -> dict:
    cleaned = _JSON_FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


# --- query_planner --------------------------------------------------------


def query_planner(state: QueryAgentState) -> dict:
    """Build a step-by-step query plan, factoring in schema + recent context."""
    logger.info("[PLANNER] query_planner")
    question = _last_user_text(state)

    descriptions = PersistentMemory().get_schema_descriptions()
    schema_context = _format_schema_descriptions(descriptions)

    prefs = state.get("user_preferences") or DEFAULT_PREFERENCES
    system = PLANNER_SYSTEM_PROMPT.format(
        schema_descriptions=schema_context,
        preferred_language=prefs.get("language", "en"),
        preferred_date_format=prefs.get("date_format", "YYYY-MM-DD"),
    )

    session_ctx = state.get("session_context") or {}
    if session_ctx.get("last_sql"):
        system += "\n\n" + PLANNER_FOLLOWUP_HINT.format(
            last_query_plan=session_ctx.get("last_query_plan") or "(none)",
            last_sql=session_ctx.get("last_sql") or "(none)",
            last_result_summary=session_ctx.get("last_result_summary") or "(none)",
        )

    llm = LLMClient().as_model()
    response = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=build_planner_user_prompt(question)),
        ]
    )
    plan = str(response.content).strip()

    return {
        "query_plan": plan,
        "iteration": state.get("iteration", 0),
    }


# --- sql_generator --------------------------------------------------------


def sql_generator(state: QueryAgentState) -> dict:
    """Translate the plan into a single PostgreSQL SELECT."""
    logger.info("[GENERATOR] sql_generator")
    settings = get_settings()
    prefs = state.get("user_preferences") or DEFAULT_PREFERENCES
    max_rows = prefs.get("max_results", settings.sql.max_rows)
    date_format = prefs.get("date_format", "YYYY-MM-DD")

    system = GENERATOR_SYSTEM_PROMPT.format(max_rows=max_rows, date_format=date_format)
    question = _last_user_text(state)
    plan = state.get("query_plan", "")

    # If the critic previously failed, fold its feedback into the regen prompt.
    critic_feedback = ""
    validation = state.get("sql_validation") or {}
    if validation.get("status") == "failed":
        issues = validation.get("issues") or []
        suggestions = validation.get("suggestions") or []
        critic_feedback = (
            "\n\nCritic feedback to address:\nIssues: "
            + "; ".join(issues)
            + "\nSuggestions: "
            + "; ".join(suggestions)
        )

    user_prompt = build_generator_user_prompt(plan, question) + critic_feedback

    llm = LLMClient().as_model()
    response = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=user_prompt)]
    )
    sql = _strip_sql_fences(str(response.content))

    return {
        "generated_sql": sql,
        "iteration": state.get("iteration", 0) + 1,
    }


# --- sql_critic -----------------------------------------------------------


def _existing_tables() -> set[str]:
    return set(inspect_schema()["tables"])


def sql_critic(state: QueryAgentState) -> dict:
    """Three-layer validation: code safety → schema existence → LLM semantic."""
    logger.info("[CRITIC] sql_critic")
    sql = state.get("generated_sql") or ""
    question = _last_user_text(state)

    issues: list[str] = []
    suggestions: list[str] = []

    # 1. Safety
    is_safe, safety_issues = validate_sql_safety(sql)
    if not is_safe:
        issues.extend(safety_issues)

    # 2. Schema — FROM/JOIN targets must exist in the public schema.
    # The regex can produce false positives (e.g. EXTRACT(month FROM
    # payment_date)), so only flag as error when NO referenced name
    # matches a real table.
    if is_safe:
        referenced = {m.lower() for m in _FROM_OR_JOIN.findall(sql)}
        existing = _existing_tables()
        known = referenced & existing
        unknown = sorted(referenced - existing)
        if not known and referenced:
            issues.append(f"Unknown tables referenced: {', '.join(unknown)}")
            suggestions.append("Check the schema and use only existing public tables.")
        elif unknown:
            suggestions.append(
                f"Possible false-positive table references: {', '.join(unknown)}"
            )

    # 3. Semantic — only ask LLM if the structural checks passed. The semantic
    # verdict is advisory only; safety/schema failures block, semantic concerns
    # become suggestions on the first pass and are ignored on retries to avoid
    # infinite loops.
    if not issues:
        try:
            llm = LLMClient().as_model()
            response = llm.invoke(
                [
                    SystemMessage(
                        content=CRITIC_SEMANTIC_PROMPT.format(
                            question=question, sql=sql
                        )
                    )
                ]
            )
            verdict = _parse_json_object(str(response.content))
            if not verdict.get("answers_question"):
                suggestions.append(f"Semantic concern: {verdict.get('reason', '')}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Semantic critic skipped: %s", exc)

    status = "passed" if not issues else "failed"
    return {
        "sql_validation": {
            "status": status,
            "issues": issues,
            "suggestions": suggestions,
        }
    }


# --- sql_confirm (conditional HITL) ---------------------------------------


def _needs_confirmation(sql: str, prefs: dict[str, Any]) -> bool:
    """Spec §8.5: HITL if 4+ joins, no LIMIT, or user opt-in."""
    if prefs.get("confirm_before_execute"):
        return True
    if not _HAS_LIMIT.search(sql):
        return True
    table_count = len(set(m.lower() for m in _FROM_OR_JOIN.findall(sql)))
    if table_count >= 4:
        return True
    return False


def sql_confirm(state: QueryAgentState) -> dict:
    """Pause for user approval only when the SQL is risky or user opted in.

    Uses ``langgraph.types.interrupt`` so the graph itself decides whether to
    pause — no need for ``interrupt_before`` at compile time.
    """
    logger.info("[CONFIRM] sql_confirm")
    sql = state.get("generated_sql") or ""
    prefs = state.get("user_preferences") or DEFAULT_PREFERENCES

    if not _needs_confirmation(sql, prefs):
        return {
            "sql_approved": True,
            "messages": [AIMessage(content="Auto-approved (low-risk query).")],
        }

    user_input = interrupt(
        {
            "sql": sql,
            "prompt": "Review the generated SQL. Reply 'approve' or 'reject'.",
        }
    )
    text = str(user_input or "").strip().lower()
    approved = text in {"approve", "approved", "ok", "yes"}
    reply = "Query approved." if approved else "Query rejected by user."
    return {
        "sql_approved": approved,
        "messages": [AIMessage(content=reply)],
    }


# --- sql_executor ---------------------------------------------------------


def sql_executor(state: QueryAgentState) -> dict:
    """Execute the approved SQL via the MCP read-only execute_sql tool."""
    logger.info("[EXECUTOR] sql_executor")
    sql = state.get("generated_sql") or ""
    settings = get_settings()
    prefs = state.get("user_preferences") or DEFAULT_PREFERENCES

    max_rows = min(
        int(prefs.get("max_results", settings.sql.max_rows)),
        settings.sql.max_rows,
    )
    timeout = settings.sql.timeout_seconds

    try:
        result = mcp_execute_sql(sql, max_rows=max_rows, timeout_seconds=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Executor failed")
        return {"error": str(exc)}

    return {"query_result": result}


# --- result_presenter -----------------------------------------------------


def result_presenter(state: QueryAgentState) -> dict:
    """Format results in NL and update the session's short-term memory."""
    logger.info("[PRESENTER] result_presenter")
    prefs = state.get("user_preferences") or DEFAULT_PREFERENCES
    question = _last_user_text(state)
    sql = state.get("generated_sql") or ""
    result = state.get("query_result") or {}

    system = PRESENTER_SYSTEM_PROMPT.format(
        preferred_language=prefs.get("language", "en"),
        preferred_date_format=prefs.get("date_format", "YYYY-MM-DD"),
    )
    user_prompt = build_presenter_user_prompt(question, sql, result)

    llm = LLMClient().as_model()
    response = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=user_prompt)]
    )
    text = str(response.content).strip()

    # Persist to short-term memory so the next /chat call can detect follow-ups.
    session_id = state.get("session_id")
    if session_id:
        mem = get_short_term_memory()
        mem.set_context(session_id, "last_sql", sql)
        mem.set_context(session_id, "last_query_plan", state.get("query_plan"))
        summary = f"{result.get('row_count', 0)} row(s) returned"
        mem.set_context(session_id, "last_result_summary", summary)
        mem.add_message(session_id, "user", question)
        mem.add_message(session_id, "assistant", text)

    return {
        "formatted_response": text,
        "messages": [AIMessage(content=text)],
    }


# --- error_response -------------------------------------------------------


def error_response(state: QueryAgentState) -> dict:
    """Terminal error node — produces a user-facing error message."""
    logger.info("[ERROR] error_response")
    err = state.get("error") or "Could not produce a valid query for that question."
    validation = state.get("sql_validation") or {}
    if validation.get("status") == "failed":
        err = "I could not generate a valid SQL query: " + "; ".join(
            validation.get("issues") or []
        )
    response = err
    return {
        "formatted_response": response,
        "messages": [AIMessage(content=response)],
    }
