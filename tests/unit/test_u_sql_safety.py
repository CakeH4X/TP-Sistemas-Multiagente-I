"""Unit tests for src/tools/sql_safety.py."""

import pytest

from tools.sql_safety import validate_sql_safety


def test_simple_select_is_safe():
    ok, issues = validate_sql_safety("SELECT * FROM film")
    assert ok is True
    assert issues == []


def test_select_with_trailing_semicolon_is_safe():
    ok, issues = validate_sql_safety("SELECT * FROM film;")
    assert ok is True, issues


def test_cte_with_select_is_safe():
    ok, issues = validate_sql_safety(
        "WITH top_films AS (SELECT * FROM film LIMIT 10) SELECT * FROM top_films"
    )
    assert ok is True, issues


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO film (title) VALUES ('x')",
        "UPDATE film SET title = 'x'",
        "DELETE FROM film",
        "DROP TABLE film",
        "ALTER TABLE film ADD COLUMN x INT",
        "TRUNCATE film",
        "CREATE TABLE y (x INT)",
        "GRANT ALL ON film TO public",
        "REVOKE ALL ON film FROM public",
        "COPY film TO '/tmp/x.csv'",
    ],
)
def test_write_statements_are_rejected(sql):
    ok, issues = validate_sql_safety(sql)
    assert ok is False
    assert any(
        "forbidden write keywords" in i or "must start with SELECT" in i for i in issues
    )


def test_multi_statement_is_rejected():
    ok, issues = validate_sql_safety("SELECT 1; SELECT 2")
    assert ok is False
    assert any(
        "semicolon" in i.lower() or "multi-statement" in i.lower() for i in issues
    )


def test_line_comment_is_rejected():
    ok, issues = validate_sql_safety("SELECT * FROM film -- comment")
    assert ok is False
    assert any("--" in i for i in issues)


def test_block_comment_is_rejected():
    ok, issues = validate_sql_safety("SELECT /* comment */ * FROM film")
    assert ok is False
    assert any("/*" in i for i in issues)


@pytest.mark.parametrize(
    "schema", ["pg_catalog", "information_schema", "agent_metadata"]
)
def test_forbidden_schema_is_rejected(schema):
    ok, issues = validate_sql_safety(f"SELECT * FROM {schema}.tables")
    assert ok is False
    assert any(schema in i for i in issues)


def test_pg_sleep_is_rejected():
    ok, issues = validate_sql_safety("SELECT pg_sleep(10)")
    assert ok is False
    assert any("pg_sleep" in i for i in issues)


def test_pg_terminate_backend_is_rejected():
    ok, issues = validate_sql_safety("SELECT pg_terminate_backend(123)")
    assert ok is False
    assert any("pg_terminate_backend" in i for i in issues)


def test_empty_sql_is_rejected():
    ok, issues = validate_sql_safety("")
    assert ok is False
    assert any("empty" in i.lower() for i in issues)


def test_whitespace_only_is_rejected():
    ok, issues = validate_sql_safety("   \n  \t  ")
    assert ok is False


def test_non_select_starting_keyword_rejected():
    ok, issues = validate_sql_safety("EXPLAIN SELECT * FROM film")
    assert ok is False
    assert any("must start with SELECT" in i for i in issues)


def test_complex_join_is_safe():
    sql = (
        "SELECT f.title, a.first_name FROM film f "
        "JOIN film_actor fa ON fa.film_id = f.film_id "
        "JOIN actor a ON a.actor_id = fa.actor_id "
        "WHERE a.last_name = 'GUINESS' LIMIT 50"
    )
    ok, issues = validate_sql_safety(sql)
    assert ok is True, issues


def test_select_from_public_schema_explicit_is_safe():
    ok, issues = validate_sql_safety("SELECT * FROM public.film LIMIT 5")
    assert ok is True, issues
