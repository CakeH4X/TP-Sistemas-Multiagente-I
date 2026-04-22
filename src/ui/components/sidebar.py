"""Streamlit sidebar — user identity, preferences, connection status."""

from __future__ import annotations

import logging

import streamlit as st

from ui.api_client import AgentAPIClient

logger = logging.getLogger(__name__)

LANGUAGES = ["en", "es"]
DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"]


def _connection_status(client: AgentAPIClient) -> tuple[str, str]:
    """Return ``(label, color)`` describing backend reachability."""
    try:
        health = client.health()
        api = "online"
        db = health.get("database", "unknown")
        if db == "connected":
            return f"API {api} · DB {db}", "green"
        return f"API {api} · DB {db}", "orange"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check failed: %s", exc)
        return f"API offline ({exc.__class__.__name__})", "red"


def _load_preferences_into_state(client: AgentAPIClient, user_id: str) -> None:
    """Pull the user's saved prefs and seed widget defaults."""
    try:
        body = client.get_preferences(user_id)
        prefs = body.get("preferences", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load preferences: %s", exc)
        prefs = {}

    st.session_state.prefs_language = prefs.get("language", "en")
    st.session_state.prefs_date_format = prefs.get("date_format", "YYYY-MM-DD")
    st.session_state.prefs_max_results = int(prefs.get("max_results", 50))
    st.session_state.prefs_confirm = bool(prefs.get("confirm_before_execute", False))
    st.session_state.prefs_show_sql = bool(prefs.get("show_sql", True))
    st.session_state.prefs_loaded_for = user_id


def render_sidebar(client: AgentAPIClient) -> None:
    """Render the sidebar widgets and persist preference edits."""
    with st.sidebar:
        st.header("Settings")

        # User ID
        user_id = st.text_input(
            "User ID",
            value=st.session_state.get("user_id", "alice"),
            help="Identifies you to the agent. Preferences are scoped per user.",
        )
        if user_id != st.session_state.get("user_id"):
            st.session_state.user_id = user_id
            _load_preferences_into_state(client, user_id)
            st.rerun()

        # First-time hydration
        if st.session_state.get("prefs_loaded_for") != user_id:
            _load_preferences_into_state(client, user_id)

        st.divider()
        st.subheader("Preferences")

        st.selectbox(
            "Language",
            LANGUAGES,
            key="prefs_language",
            index=LANGUAGES.index(st.session_state.prefs_language),
        )
        st.selectbox(
            "Date format",
            DATE_FORMATS,
            key="prefs_date_format",
            index=DATE_FORMATS.index(st.session_state.prefs_date_format),
        )
        st.number_input(
            "Max results",
            min_value=1,
            max_value=500,
            step=10,
            key="prefs_max_results",
        )
        st.toggle(
            "Confirm before execute",
            key="prefs_confirm",
            help="Always show the SQL for review before running it.",
        )
        st.toggle("Show SQL in chat", key="prefs_show_sql")

        if st.button("Save preferences", type="primary", use_container_width=True):
            try:
                client.update_preferences(
                    user_id,
                    {
                        "language": st.session_state.prefs_language,
                        "date_format": st.session_state.prefs_date_format,
                        "max_results": st.session_state.prefs_max_results,
                        "confirm_before_execute": st.session_state.prefs_confirm,
                        "show_sql": st.session_state.prefs_show_sql,
                    },
                )
                st.success("Preferences saved.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not save preferences: {exc}")

        st.divider()
        st.subheader("Session")
        st.caption(f"session_id: `{st.session_state.session_id[:8]}…`")
        if st.button("New conversation", use_container_width=True):
            from uuid import uuid4

            st.session_state.session_id = str(uuid4())
            st.session_state.thread_id = None
            st.session_state.messages = []
            st.session_state.pending_review = None
            st.rerun()

        st.divider()
        label, color = _connection_status(client)
        st.markdown(
            f"<span style='color:{color};'>●</span> {label}",
            unsafe_allow_html=True,
        )
