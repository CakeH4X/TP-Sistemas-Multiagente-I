"""Streamlit Schema tab — auto-discover schema, review with HITL, persist."""

from __future__ import annotations

import logging

import streamlit as st

from ui.api_client import AgentAPIClient

logger = logging.getLogger(__name__)


def _start_analysis(client: AgentAPIClient) -> None:
    """Kick off a fresh schema analysis run."""
    try:
        response = client.schema_analyze(
            session_id=st.session_state.session_id,
            user_id=st.session_state.user_id,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to start schema analysis: {exc}")
        return

    if response.get("status") == "pending_review":
        st.session_state.schema_pending = {
            "thread_id": response["thread_id"],
            "generated_descriptions": (response.get("review_data") or {}).get(
                "generated_descriptions", {}
            ),
        }
    else:
        st.session_state.schema_pending = None
        st.session_state.schema_last_message = response.get("message")
    st.rerun()


def _resume(client: AgentAPIClient, message: str) -> None:
    pending = st.session_state.schema_pending
    try:
        response = client.schema_analyze(
            session_id=st.session_state.session_id,
            user_id=st.session_state.user_id,
            thread_id=pending["thread_id"],
            message=message,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to resume schema review: {exc}")
        return

    if response.get("status") == "pending_review":
        # Revision cycle returned a new draft — replace the pending block.
        st.session_state.schema_pending = {
            "thread_id": response["thread_id"],
            "generated_descriptions": (response.get("review_data") or {}).get(
                "generated_descriptions", {}
            ),
        }
    else:
        st.session_state.schema_pending = None
        st.session_state.schema_last_message = response.get("message")
    st.rerun()


def _render_descriptions(descriptions: dict[str, dict[str, str]]) -> None:
    if not descriptions:
        st.info("No descriptions returned.")
        return
    for table, cols in sorted(descriptions.items()):
        table_desc = cols.get("__table__", "(no table description)")
        with st.expander(f"📄  {table} — {table_desc}", expanded=False):
            for col, desc in sorted(cols.items()):
                if col == "__table__":
                    continue
                st.markdown(f"**`{col}`** — {desc}")


def render_schema(client: AgentAPIClient) -> None:
    """Render the Schema Documentation tab."""
    st.subheader("Schema Documentation")
    st.caption(
        "The Schema Agent auto-discovers all tables and proposes "
        "descriptions. Review them here before saving."
    )

    pending = st.session_state.get("schema_pending")
    last_message = st.session_state.get("schema_last_message")

    if pending is None:
        if last_message:
            st.success(last_message)
        if st.button(
            "Analyze full schema",
            type="primary",
            use_container_width=True,
            key="schema_start",
        ):
            _start_analysis(client)
        st.divider()
        st.markdown("**Currently persisted descriptions**")
        try:
            descs = client.get_schema_descriptions()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load saved descriptions: {exc}")
            descs = {}
        _render_descriptions(descs)
        return

    # --- pending review block --------------------------------------------
    st.warning("Review the proposed descriptions, then approve or revise.")
    _render_descriptions(pending["generated_descriptions"])

    st.divider()
    revision = st.text_area(
        "Optional revision feedback",
        placeholder="e.g. Make descriptions shorter; clarify foreign keys.",
        key="schema_revision_input",
    )

    cols = st.columns(3)
    if cols[0].button(
        "Approve all", type="primary", use_container_width=True, key="schema_approve"
    ):
        _resume(client, "approve")
    if cols[1].button(
        "Request revisions", use_container_width=True, key="schema_revise"
    ):
        feedback = (revision or "Please revise the descriptions.").strip()
        _resume(client, feedback)
    if cols[2].button("Cancel", use_container_width=True, key="schema_cancel"):
        _resume(client, "reject")
