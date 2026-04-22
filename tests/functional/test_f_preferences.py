"""Functional tests for /preferences/{user_id} (real DB)."""

from __future__ import annotations

import uuid

import psycopg
import pytest

import config.settings as settings_module
from memory.persistent import DEFAULT_PREFERENCES


@pytest.fixture(autouse=True)
def _reset_settings():
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture
def cleanup_user_prefs():
    user_ids: list[str] = []
    yield user_ids
    if not user_ids:
        return
    settings = settings_module.get_settings()
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {settings.db.metadata_schema}.user_preferences "
            "WHERE user_id = ANY(%s)",
            (user_ids,),
        )
        conn.commit()


def _uid() -> str:
    return f"phase6-test-{uuid.uuid4().hex[:8]}"


def test_get_preferences_returns_defaults_for_unknown_user(test_client):
    user_id = _uid()
    response = test_client.get(f"/preferences/{user_id}")
    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == user_id
    assert body["preferences"] == DEFAULT_PREFERENCES


def test_put_preferences_persists_and_returns_merged(test_client, cleanup_user_prefs):
    user_id = _uid()
    cleanup_user_prefs.append(user_id)

    response = test_client.put(
        f"/preferences/{user_id}",
        json={"preferences": {"language": "es", "max_results": 25}},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["preferences"]["language"] == "es"
    assert body["preferences"]["max_results"] == 25
    # Defaults preserved for keys not in the update
    assert body["preferences"]["date_format"] == DEFAULT_PREFERENCES["date_format"]


def test_put_preferences_subsequent_get_returns_same_values(
    test_client, cleanup_user_prefs
):
    user_id = _uid()
    cleanup_user_prefs.append(user_id)

    test_client.put(
        f"/preferences/{user_id}",
        json={"preferences": {"language": "es", "show_sql": False}},
    )
    body = test_client.get(f"/preferences/{user_id}").json()

    assert body["preferences"]["language"] == "es"
    assert body["preferences"]["show_sql"] is False


def test_put_preferences_upserts_on_repeated_update(test_client, cleanup_user_prefs):
    user_id = _uid()
    cleanup_user_prefs.append(user_id)

    test_client.put(f"/preferences/{user_id}", json={"preferences": {"language": "en"}})
    test_client.put(f"/preferences/{user_id}", json={"preferences": {"language": "es"}})
    body = test_client.get(f"/preferences/{user_id}").json()

    assert body["preferences"]["language"] == "es"


def test_put_preferences_supports_arbitrary_jsonable_values(
    test_client, cleanup_user_prefs
):
    user_id = _uid()
    cleanup_user_prefs.append(user_id)

    payload = {"preferences": {"custom_filter": {"min_year": 2000, "tags": ["new"]}}}
    response = test_client.put(f"/preferences/{user_id}", json=payload)
    assert response.status_code == 200

    body = test_client.get(f"/preferences/{user_id}").json()
    assert body["preferences"]["custom_filter"] == {
        "min_year": 2000,
        "tags": ["new"],
    }


def test_put_preferences_rejects_empty_payload(test_client):
    response = test_client.put(f"/preferences/{_uid()}", json={"preferences": {}})
    assert response.status_code == 400


def test_get_default_preferences_returns_full_defaults(test_client):
    response = test_client.get(f"/preferences/{_uid()}/defaults")
    assert response.status_code == 200
    assert response.json() == DEFAULT_PREFERENCES


def test_preferences_isolated_between_users(test_client, cleanup_user_prefs):
    a, b = _uid(), _uid()
    cleanup_user_prefs.extend([a, b])

    test_client.put(f"/preferences/{a}", json={"preferences": {"language": "es"}})
    test_client.put(f"/preferences/{b}", json={"preferences": {"language": "en"}})

    assert (
        test_client.get(f"/preferences/{a}").json()["preferences"]["language"] == "es"
    )
    assert (
        test_client.get(f"/preferences/{b}").json()["preferences"]["language"] == "en"
    )
