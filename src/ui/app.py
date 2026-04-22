"""Streamlit entry point for the NL Query Agent web UI."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_client import AgentAPIClient
from ui.components.chat import render_chat
from ui.components.schema_review import render_schema
from ui.components.sidebar import render_sidebar


def _bootstrap_session_state() -> None:
    """Initialize session_state keys exactly once per browser session."""
    defaults = {
        "session_id": str(uuid4()),
        "user_id": "alice",
        "thread_id": None,
        "messages": [],
        "pending_review": None,
        "schema_pending": None,
        "schema_last_message": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def main() -> None:
    st.set_page_config(
        page_title="DVD Rental NL Query Agent",
        layout="wide",
        page_icon="🎬",
    )

    _bootstrap_session_state()
    client = AgentAPIClient()

    render_sidebar(client)

    st.title("DVD Rental NL Query Agent")
    tab_chat, tab_schema = st.tabs(["Query Agent", "Schema Documentation"])
    with tab_chat:
        render_chat(client)
    with tab_schema:
        render_schema(client)


main()
