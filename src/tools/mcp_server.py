"""MCP server exposing three PostgreSQL tools for the DVD Rental database.

Runs as a standalone process over stdio. Spawned by ``mcp_client.py`` via
``langchain-mcp-adapters`` ``MultiServerMCPClient``.

All database operations use a read-only transaction. The DVD Rental database
is the only target; system schemas (``pg_catalog``, ``information_schema``) and
the ``agent_metadata`` schema are excluded from schema introspection.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import psycopg
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

from config.settings import get_settings
from tools.sql_safety import validate_sql_safety

logger = logging.getLogger(__name__)

mcp = FastMCP("dvdrental")

_PUBLIC = "public"


def _connect() -> psycopg.Connection:
    """Open a new psycopg connection to the DVD Rental database."""
    settings = get_settings()
    return psycopg.connect(settings.db.database_url, row_factory=dict_row)


def _list_tables(conn: psycopg.Connection) -> list[str]:
    """Return all base tables in the ``public`` schema."""
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (_PUBLIC,),
    ).fetchall()
    return [r["table_name"] for r in rows]


def _table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (_PUBLIC, table_name),
    ).fetchone()
    return row is not None


def _describe_table(conn: psycopg.Connection, table_name: str) -> dict[str, Any]:
    """Return columns, primary key, foreign keys, indexes, and row count."""
    columns = conn.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (_PUBLIC, table_name),
    ).fetchall()

    pk = conn.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema   = kcu.table_schema
        WHERE tc.table_schema = %s
          AND tc.table_name   = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """,
        (_PUBLIC, table_name),
    ).fetchall()

    fks = conn.execute(
        """
        SELECT
            kcu.column_name        AS column_name,
            ccu.table_name         AS references_table,
            ccu.column_name        AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema    = tc.table_schema
        WHERE tc.table_schema   = %s
          AND tc.table_name     = %s
          AND tc.constraint_type = 'FOREIGN KEY'
        """,
        (_PUBLIC, table_name),
    ).fetchall()

    indexes = conn.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s AND tablename = %s
        ORDER BY indexname
        """,
        (_PUBLIC, table_name),
    ).fetchall()

    count_row = conn.execute(
        f'SELECT COUNT(*) AS n FROM "{_PUBLIC}"."{table_name}"'
    ).fetchone()
    row_count = int(count_row["n"]) if count_row else 0

    return {
        "table_name": table_name,
        "columns": columns,
        "primary_key": [r["column_name"] for r in pk],
        "foreign_keys": fks,
        "indexes": indexes,
        "row_count": row_count,
    }


@mcp.tool()
def inspect_schema(table_name: str | None = None) -> dict[str, Any]:
    """Inspect the DVD Rental schema.

    Without ``table_name``: returns the list of all public tables.
    With ``table_name``: returns columns, primary key, foreign keys, indexes,
    and row count for that table. The table name is validated against
    ``information_schema.tables`` to prevent SQL injection.
    """
    with _connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        if table_name is None:
            return {"tables": _list_tables(conn)}
        if not _table_exists(conn, table_name):
            raise ValueError(f"Unknown table: {table_name!r}")
        return _describe_table(conn, table_name)


@mcp.tool()
def execute_sql(
    sql: str, max_rows: int = 100, timeout_seconds: int = 30
) -> dict[str, Any]:
    """Execute a read-only SELECT and return up to ``max_rows`` rows.

    Uses ``SET TRANSACTION READ ONLY`` and ``statement_timeout`` at the
    session level. Rejects anything failing :func:`validate_sql_safety`.
    """
    is_safe, issues = validate_sql_safety(sql)
    if not is_safe:
        raise ValueError(f"Unsafe SQL: {'; '.join(issues)}")

    settings = get_settings()
    effective_max = min(max_rows, settings.sql.max_rows)
    effective_timeout_ms = min(timeout_seconds, settings.sql.timeout_seconds) * 1000

    started = time.perf_counter()
    with _connect() as conn:
        conn.execute(f"SET statement_timeout = {effective_timeout_ms}")
        conn.execute("SET TRANSACTION READ ONLY")
        cur = conn.execute(sql)
        rows = cur.fetchmany(effective_max + 1)
        columns = [d.name for d in cur.description] if cur.description else []

    truncated = len(rows) > effective_max
    rows = rows[:effective_max]
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "execution_time_ms": round(elapsed_ms, 3),
    }


@mcp.tool()
def get_table_sample(table_name: str, limit: int = 5) -> dict[str, Any]:
    """Return up to ``limit`` sample rows from ``table_name`` plus total row count."""
    with _connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        if not _table_exists(conn, table_name):
            raise ValueError(f"Unknown table: {table_name!r}")

        # table_name now verified — safe to interpolate as quoted identifier.
        quoted = f'"{_PUBLIC}"."{table_name}"'
        cur = conn.execute(f"SELECT * FROM {quoted} LIMIT %s", (limit,))
        rows = cur.fetchall()
        columns = [d.name for d in cur.description] if cur.description else []

        total = conn.execute(f"SELECT COUNT(*) AS n FROM {quoted}").fetchone()
        total_rows = int(total["n"]) if total else 0

    return {
        "table_name": table_name,
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
    }


def main() -> None:
    """Entry point when run as ``python -m tools.mcp_server``."""
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
