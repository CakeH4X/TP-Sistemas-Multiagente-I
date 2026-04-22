"""LLM client using LangChain's ChatOpenAI against the LiteLLM proxy.

Never import provider-specific SDKs directly. All LLM calls go through
the LiteLLM proxy at settings.llm.base_url.
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from config.settings import get_settings


class LLMClient:
    """Client wrapping ChatOpenAI pointed at the LiteLLM proxy."""

    def __init__(self) -> None:
        settings = get_settings()
        self._llm = ChatOpenAI(
            base_url=f"{settings.llm.base_url.rstrip('/')}/v1",
            api_key=settings.llm.api_key or "dummy-key",
            model=settings.llm.model,
            temperature=0.0,
        )

    def bind_tools(self, tools: list) -> BaseChatModel:
        """Return the model bound with the given tools (for ReAct-style tool use)."""
        return self._llm.bind_tools(tools)

    def as_model(self) -> BaseChatModel:
        """Expose the underlying LangChain chat model for message-based calls."""
        return self._llm
