"""Unit tests for src/llm/client.py."""

from unittest.mock import MagicMock, patch

import llm.client as llm_client_module


def test_llm_client_uses_correct_base_url(monkeypatch):
    # Given: a known LLM_SERVICE_URL
    monkeypatch.setenv("LLM_SERVICE_URL", "https://my-proxy.example.com")

    import config.settings as settings_module

    settings_module._settings = None

    # When: LLMClient is constructed
    with patch.object(llm_client_module, "ChatOpenAI") as mock_chat:
        llm_client_module.LLMClient()

    # Then: ChatOpenAI was called with /v1 appended
    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["base_url"] == "https://my-proxy.example.com/v1"

    # Clean up
    settings_module._settings = None


def test_llm_client_uses_correct_model(monkeypatch):
    # Given
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1")

    import config.settings as settings_module

    settings_module._settings = None

    # When
    with patch.object(llm_client_module, "ChatOpenAI") as mock_chat:
        llm_client_module.LLMClient()

    # Then
    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4.1"

    # Clean up
    settings_module._settings = None


def test_llm_client_uses_dummy_key_when_empty(monkeypatch):
    # Given: no API key set
    monkeypatch.setenv("LLM_API_KEY", "")

    import config.settings as settings_module

    settings_module._settings = None

    # When
    with patch.object(llm_client_module, "ChatOpenAI") as mock_chat:
        llm_client_module.LLMClient()

    # Then: falls back to "dummy-key" to avoid ChatOpenAI validation error
    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["api_key"] == "dummy-key"

    # Clean up
    settings_module._settings = None


def test_llm_client_bind_tools_delegates():
    # Given
    mock_llm = MagicMock()
    with patch.object(llm_client_module, "ChatOpenAI", return_value=mock_llm):
        client = llm_client_module.LLMClient()

    tools = [object()]

    # When
    client.bind_tools(tools)

    # Then: delegates to underlying _llm
    mock_llm.bind_tools.assert_called_once_with(tools)


def test_llm_client_as_model_returns_underlying_llm():
    # Given
    mock_llm = MagicMock()
    with patch.object(llm_client_module, "ChatOpenAI", return_value=mock_llm):
        client = llm_client_module.LLMClient()

    # When
    model = client.as_model()

    # Then
    assert model is mock_llm
