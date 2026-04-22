"""Short-term memory: in-process session state scoped by ``session_id``.

Does not survive process restarts. Truncates the message list by dropping
oldest messages once it exceeds ``max_messages``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionContext:
    """Per-session working memory."""

    messages: list[dict[str, str]] = field(default_factory=list)
    last_sql: str | None = None
    last_query_plan: str | None = None
    last_result_summary: str | None = None
    assumptions: list[str] = field(default_factory=list)
    recent_tables: set[str] = field(default_factory=set)
    extra: dict[str, Any] = field(default_factory=dict)


class ShortTermMemory:
    """In-memory store of ``SessionContext`` keyed by ``session_id``."""

    def __init__(self, max_messages: int = 50) -> None:
        self._max_messages = max_messages
        self._sessions: dict[str, SessionContext] = {}

    def get_session(self, session_id: str) -> SessionContext:
        """Return the ``SessionContext`` for ``session_id`` (creating if missing)."""
        ctx = self._sessions.get(session_id)
        if ctx is None:
            ctx = SessionContext()
            self._sessions[session_id] = ctx
        return ctx

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message, dropping oldest once over ``max_messages``."""
        ctx = self.get_session(session_id)
        ctx.messages.append({"role": role, "content": content})
        overflow = len(ctx.messages) - self._max_messages
        if overflow > 0:
            del ctx.messages[:overflow]

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        return list(self.get_session(session_id).messages)

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        """Set a named value. Known fields update the dataclass; unknown ones
        go into ``extra`` so agents can stash arbitrary state without schema changes.
        """
        ctx = self.get_session(session_id)
        if hasattr(ctx, key) and key != "extra":
            setattr(ctx, key, value)
        else:
            ctx.extra[key] = value

    def get_context(self, session_id: str, key: str) -> Any | None:
        ctx = self.get_session(session_id)
        if hasattr(ctx, key) and key != "extra":
            return getattr(ctx, key)
        return ctx.extra.get(key)

    def reset(self, session_id: str) -> None:
        """Drop a session's state (used by 'New Conversation' in the UI)."""
        self._sessions.pop(session_id, None)
