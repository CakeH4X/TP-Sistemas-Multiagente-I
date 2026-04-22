"""Tests for ``src/memory/persistent.py``.

Hits the real PostgreSQL instance (via conftest's ``DATABASE_URL`` default)
so the ``agent_metadata`` tables exercised are the actual ones init-scripted
into the container. Each test cleans up its own rows to stay independent.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

import config.settings as settings_module
from memory.persistent import DEFAULT_PREFERENCES, PersistentMemory


@pytest.fixture(autouse=True)
def _reset_settings():
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture
def store() -> PersistentMemory:
    return PersistentMemory()


@pytest.fixture
def cleanup():
    user_ids: list[str] = []
    table_names: list[str] = []

    yield user_ids, table_names

    settings = settings_module.get_settings()
    schema = settings.db.metadata_schema
    with psycopg.connect(settings.db.database_url) as conn, conn.cursor() as cur:
        if user_ids:
            cur.execute(
                f"DELETE FROM {schema}.user_preferences WHERE user_id = ANY(%s)",
                (user_ids,),
            )
        if table_names:
            cur.execute(
                f"DELETE FROM {schema}.schema_descriptions WHERE table_name = ANY(%s)",
                (table_names,),
            )
        conn.commit()


def _uid() -> str:
    return f"test-user-{uuid.uuid4().hex[:8]}"


def _tname() -> str:
    return f"test_tbl_{uuid.uuid4().hex[:8]}"


# --- User preferences -----------------------------------------------------


def test_get_user_preferences_returns_defaults_for_unknown_user(store, cleanup):
    prefs = store.get_user_preferences(_uid())
    assert prefs == DEFAULT_PREFERENCES


def test_set_user_preference_persists_value(store, cleanup):
    user_ids, _ = cleanup
    user_id = _uid()
    user_ids.append(user_id)

    store.set_user_preference(user_id, "language", "es")
    prefs = store.get_user_preferences(user_id)

    assert prefs["language"] == "es"
    # Other defaults still present
    assert prefs["date_format"] == DEFAULT_PREFERENCES["date_format"]


def test_set_user_preference_upserts_existing_value(store, cleanup):
    user_ids, _ = cleanup
    user_id = _uid()
    user_ids.append(user_id)

    store.set_user_preference(user_id, "max_results", 25)
    store.set_user_preference(user_id, "max_results", 200)
    prefs = store.get_user_preferences(user_id)

    assert prefs["max_results"] == 200


def test_set_user_preference_supports_complex_json_values(store, cleanup):
    user_ids, _ = cleanup
    user_id = _uid()
    user_ids.append(user_id)

    payload = {"nested": [1, 2, 3], "flag": True}
    store.set_user_preference(user_id, "custom", payload)
    prefs = store.get_user_preferences(user_id)

    assert prefs["custom"] == payload


def test_preferences_are_isolated_between_users(store, cleanup):
    user_ids, _ = cleanup
    a, b = _uid(), _uid()
    user_ids.extend([a, b])

    store.set_user_preference(a, "language", "es")
    store.set_user_preference(b, "language", "en")

    assert store.get_user_preferences(a)["language"] == "es"
    assert store.get_user_preferences(b)["language"] == "en"


# --- Schema descriptions --------------------------------------------------


def test_save_and_get_schema_descriptions_roundtrip(store, cleanup):
    _, table_names = cleanup
    tbl = _tname()
    table_names.append(tbl)

    descriptions = {
        tbl: {
            "__table__": "Test table.",
            "col_a": "The first column.",
            "col_b": "The second column.",
        }
    }
    store.save_schema_descriptions(descriptions, approved_by="tester")
    fetched = store.get_schema_descriptions(tbl)

    assert fetched == descriptions


def test_save_schema_descriptions_upserts(store, cleanup):
    _, table_names = cleanup
    tbl = _tname()
    table_names.append(tbl)

    store.save_schema_descriptions({tbl: {"__table__": "v1"}}, approved_by="tester")
    store.save_schema_descriptions({tbl: {"__table__": "v2"}}, approved_by="tester")

    fetched = store.get_schema_descriptions(tbl)
    assert fetched[tbl]["__table__"] == "v2"


def test_get_schema_descriptions_filters_by_table(store, cleanup):
    _, table_names = cleanup
    t1, t2 = _tname(), _tname()
    table_names.extend([t1, t2])

    store.save_schema_descriptions(
        {
            t1: {"__table__": "one"},
            t2: {"__table__": "two"},
        },
        approved_by="tester",
    )

    only_t1 = store.get_schema_descriptions(t1)
    assert list(only_t1.keys()) == [t1]


def test_save_empty_descriptions_is_a_no_op(store):
    store.save_schema_descriptions({}, approved_by="tester")
