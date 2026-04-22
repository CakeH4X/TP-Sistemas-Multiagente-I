"""Streamlit chat tab — Query Agent with HITL confirmation."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd
import streamlit as st

from ui.api_client import AgentAPIClient

logger = logging.getLogger(__name__)


_SQL_BLOCK = re.compile(
    r"(?:SQL ejecutado:|SQL executed:)?\s*```sql\s*.*?```\s*",
    re.DOTALL | re.IGNORECASE,
)


def _render_assistant_payload(payload: dict[str, Any]) -> None:
    """Render the assistant's full response (text + optional SQL + table)."""
    text = payload.get("message") or ""
    if not st.session_state.get("prefs_show_sql", True):
        text = _SQL_BLOCK.sub("", text).strip()
    if text:
        st.markdown(text)

    data = payload.get("data") or {}
    rows = data.get("rows") or []
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=False, hide_index=True)
        if data.get("truncated"):
            st.caption(
                f"Truncated to {data.get('row_count')} rows · "
                f"{data.get('execution_time_ms', 0):.1f} ms"
            )
        else:
            st.caption(
                f"{data.get('row_count', len(rows))} row(s) · "
                f"{data.get('execution_time_ms', 0):.1f} ms"
            )


def _render_pending_review(client: AgentAPIClient, pending: dict[str, Any]) -> None:
    """Render the SQL up for HITL approval and Approve / Reject buttons."""
    st.warning("Review the generated SQL before it runs.")
    st.code(pending["sql"], language="sql")

    cols = st.columns(2)
    if cols[0].button(
        "Approve & run",
        type="primary",
        use_container_width=True,
        key="chat_approve",
    ):
        _resume_review(client, "approve")
    if cols[1].button("Reject", use_container_width=True, key="chat_reject"):
        _resume_review(client, "reject")


def _resume_review(client: AgentAPIClient, decision: str) -> None:
    """Resume the paused thread with the user's HITL decision."""
    pending = st.session_state.pending_review
    try:
        response = client.chat(
            session_id=st.session_state.session_id,
            user_id=st.session_state.user_id,
            message=decision,
            thread_id=pending["thread_id"],
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to resume: {exc}")
        return

    st.session_state.pending_review = None
    st.session_state.thread_id = None
    st.session_state.messages.append({"role": "assistant", "payload": response})
    st.rerun()


def render_chat(client: AgentAPIClient) -> None:
    """Render the Query Agent chat tab."""
    st.subheader("Query Agent")
    st.caption(
        "Ask questions about the DVD Rental database in natural language. "
        "Risky SQL pauses for your approval."
    )

    # --- replay history ----------------------------------------------------
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                _render_assistant_payload(msg["payload"])
            else:
                st.markdown(msg["content"])

    # --- pending HITL review ---------------------------------------------
    if st.session_state.pending_review:
        with st.chat_message("assistant"):
            _render_pending_review(client, st.session_state.pending_review)
        return  # block new questions until decision is made

    # --- new question ----------------------------------------------------
    prompt = st.chat_input("Ask about the DVD Rental database…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                response = client.chat(
                    session_id=st.session_state.session_id,
                    user_id=st.session_state.user_id,
                    message=prompt,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Backend error: {exc}")
                return

        if response.get("status") == "pending_review":
            st.session_state.pending_review = {
                "thread_id": response["thread_id"],
                "sql": (response.get("review_data") or {}).get("sql"),
            }
            st.session_state.thread_id = response["thread_id"]
        else:
            st.session_state.messages.append({"role": "assistant", "payload": response})
        st.rerun()
