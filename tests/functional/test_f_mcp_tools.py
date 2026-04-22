"""Functional tests for MCP tools (requires running DVD Rental PostgreSQL)."""

import pytest

import config.settings as settings_module
from tools.mcp_server import execute_sql, get_table_sample, inspect_schema


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Ensure each test picks up conftest env overrides."""
    settings_module._settings = None
    yield
    settings_module._settings = None


EXPECTED_DVDRENTAL_TABLES = {
    "actor",
    "address",
    "category",
    "city",
    "country",
    "customer",
    "film",
    "film_actor",
    "film_category",
    "inventory",
    "language",
    "payment",
    "rental",
    "staff",
    "store",
}


def test_inspect_schema_lists_all_dvdrental_tables():
    result = inspect_schema()
    assert "tables" in result
    tables = set(result["tables"])
    assert tables == EXPECTED_DVDRENTAL_TABLES


def test_inspect_schema_film_returns_columns_and_pk():
    result = inspect_schema("film")
    assert result["table_name"] == "film"
    column_names = {c["column_name"] for c in result["columns"]}
    assert {"film_id", "title", "release_year", "language_id"} <= column_names
    assert result["primary_key"] == ["film_id"]
    assert result["row_count"] == 1000


def test_inspect_schema_film_returns_foreign_keys():
    result = inspect_schema("film_actor")
    fk_columns = {fk["column_name"] for fk in result["foreign_keys"]}
    assert {"film_id", "actor_id"} <= fk_columns


def test_inspect_schema_unknown_table_raises():
    with pytest.raises(ValueError, match="Unknown table"):
        inspect_schema("does_not_exist")


def test_execute_sql_runs_select():
    result = execute_sql("SELECT COUNT(*) AS n FROM film")
    assert result["row_count"] == 1
    assert result["columns"] == ["n"]
    assert result["rows"][0]["n"] == 1000
    assert result["truncated"] is False
    assert result["execution_time_ms"] >= 0


def test_execute_sql_respects_max_rows():
    result = execute_sql("SELECT film_id FROM film ORDER BY film_id", max_rows=5)
    assert result["row_count"] == 5
    assert result["truncated"] is True


def test_execute_sql_rejects_write_statement():
    with pytest.raises(ValueError, match="Unsafe SQL"):
        execute_sql("DELETE FROM film")


def test_execute_sql_rejects_multi_statement():
    with pytest.raises(ValueError, match="Unsafe SQL"):
        execute_sql("SELECT 1; SELECT 2")


def test_execute_sql_rejects_forbidden_schema():
    with pytest.raises(ValueError, match="Unsafe SQL"):
        execute_sql("SELECT * FROM information_schema.tables")


def test_get_table_sample_returns_rows_and_total():
    result = get_table_sample("actor", limit=3)
    assert result["table_name"] == "actor"
    assert len(result["rows"]) == 3
    assert result["total_rows"] == 200
    column_names = set(result["columns"])
    assert {"actor_id", "first_name", "last_name"} <= column_names


def test_get_table_sample_rejects_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        get_table_sample("robert'); DROP TABLE film;--", limit=1)


async def test_mcp_client_end_to_end_spawns_server_and_lists_tools():
    """Verify the full stdio pipeline: client spawns server, tools are callable."""
    from tools.mcp_client import get_mcp_tools

    tools = await get_mcp_tools()
    tool_names = {t.name for t in tools}
    assert {"inspect_schema", "execute_sql", "get_table_sample"} <= tool_names

    inspect = next(t for t in tools if t.name == "inspect_schema")
    result = await inspect.ainvoke({})
    # MCP returns content parts as list of dicts; payload is JSON text.
    text = result[0]["text"] if isinstance(result, list) else str(result)
    for table in ("film", "actor", "rental"):
        assert table in text
