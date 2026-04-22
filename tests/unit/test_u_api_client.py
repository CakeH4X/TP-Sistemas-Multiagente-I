"""Unit tests for the Streamlit-side AgentAPIClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ui.api_client import AgentAPIClient


@pytest.fixture
def client():
    return AgentAPIClient(base_url="http://test")


def _stub_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_base_url_default_uses_env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://from-env:9000")
    c = AgentAPIClient()
    assert c.base_url == "http://from-env:9000"


def test_base_url_strips_trailing_slash():
    c = AgentAPIClient(base_url="http://test/")
    assert c.base_url == "http://test"


def test_health_uses_get(client):
    with patch.object(
        client._client, "get", return_value=_stub_response({"status": "healthy"})
    ) as m:
        result = client.health()
    m.assert_called_once_with("/health", params={})
    assert result == {"status": "healthy"}


def test_chat_includes_thread_id_when_supplied(client):
    with patch.object(
        client._client, "post", return_value=_stub_response({"status": "completed"})
    ) as m:
        client.chat("s1", "u1", "hi", thread_id="tid-1")
    args, kwargs = m.call_args
    assert args[0] == "/chat"
    assert kwargs["json"] == {
        "session_id": "s1",
        "user_id": "u1",
        "message": "hi",
        "thread_id": "tid-1",
    }


def test_chat_omits_thread_id_when_none(client):
    with patch.object(
        client._client, "post", return_value=_stub_response({"status": "completed"})
    ) as m:
        client.chat("s1", "u1", "hi")
    payload = m.call_args.kwargs["json"]
    assert "thread_id" not in payload


def test_schema_analyze_omits_optional_args_when_absent(client):
    with patch.object(
        client._client,
        "post",
        return_value=_stub_response({"status": "pending_review"}),
    ) as m:
        client.schema_analyze("s1", "u1")
    assert m.call_args.kwargs["json"] == {"session_id": "s1", "user_id": "u1"}


def test_schema_analyze_includes_thread_id_and_message_when_supplied(client):
    with patch.object(
        client._client, "post", return_value=_stub_response({"status": "completed"})
    ) as m:
        client.schema_analyze("s1", "u1", thread_id="tid", message="approve")
    payload = m.call_args.kwargs["json"]
    assert payload == {
        "session_id": "s1",
        "user_id": "u1",
        "thread_id": "tid",
        "message": "approve",
    }


def test_get_schema_descriptions_passes_table_name_filter(client):
    with patch.object(
        client._client, "get", return_value=_stub_response({"film": {}})
    ) as m:
        client.get_schema_descriptions("film")
    m.assert_called_once_with("/schema/descriptions", params={"table_name": "film"})


def test_get_schema_descriptions_no_filter_uses_empty_params(client):
    with patch.object(client._client, "get", return_value=_stub_response({})) as m:
        client.get_schema_descriptions()
    m.assert_called_once_with("/schema/descriptions", params={})


def test_get_preferences_uses_user_id_in_path(client):
    with patch.object(
        client._client,
        "get",
        return_value=_stub_response({"user_id": "alice", "preferences": {}}),
    ) as m:
        client.get_preferences("alice")
    m.assert_called_once_with("/preferences/alice", params={})


def test_update_preferences_sends_payload_to_correct_path(client):
    with patch.object(
        client._client,
        "put",
        return_value=_stub_response(
            {"user_id": "alice", "preferences": {"language": "es"}}
        ),
    ) as m:
        client.update_preferences("alice", {"language": "es"})
    args, kwargs = m.call_args
    assert args[0] == "/preferences/alice"
    assert kwargs["json"] == {"preferences": {"language": "es"}}
