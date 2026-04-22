"""Thin HTTP wrapper around the FastAPI backend used by the Streamlit UI.

The UI never imports LangGraph / Postgres / MCP directly — it talks to the
backend over HTTP through this client.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentAPIClient:
    """Calls the NL Query Agent backend."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0) -> None:
        self.base_url = (
            base_url or os.environ.get("API_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # --- low-level ---------------------------------------------------------

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.get(path, params=params or {})
        response.raise_for_status()
        return response.json()

    def _put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.put(path, json=payload)
        response.raise_for_status()
        return response.json()

    # --- public surface ---------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def chat(
        self,
        session_id: str,
        user_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
        }
        if thread_id:
            payload["thread_id"] = thread_id
        return self._post("/chat", payload)

    def schema_analyze(
        self,
        session_id: str,
        user_id: str,
        thread_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"session_id": session_id, "user_id": user_id}
        if thread_id:
            payload["thread_id"] = thread_id
        if message is not None:
            payload["message"] = message
        return self._post("/schema/analyze", payload)

    def get_schema_descriptions(self, table_name: str | None = None) -> dict[str, Any]:
        params = {"table_name": table_name} if table_name else None
        return self._get("/schema/descriptions", params=params)

    def get_preferences(self, user_id: str) -> dict[str, Any]:
        return self._get(f"/preferences/{user_id}")

    def update_preferences(
        self, user_id: str, preferences: dict[str, Any]
    ) -> dict[str, Any]:
        return self._put(f"/preferences/{user_id}", {"preferences": preferences})
