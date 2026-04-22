"""Persistent memory backed by PostgreSQL in the ``agent_metadata`` schema.

Stores per-user preferences and approved schema descriptions. Tables are
created by the init scripts in ``data/init_metadata_schema.sql`` but
``_ensure_tables`` here recreates them idempotently for tests and new
deployments.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config.settings import get_settings

logger = logging.getLogger(__name__)

TABLE_LEVEL_KEY = "__table__"

DEFAULT_PREFERENCES: dict[str, Any] = {
    "language": "en",
    "date_format": "YYYY-MM-DD",
    "max_results": 50,
    "confirm_before_execute": False,
    "show_sql": True,
}

_CREATE_PREFERENCES_SQL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.user_preferences (
    user_id VARCHAR(255) NOT NULL,
    preference_key VARCHAR(255) NOT NULL,
    preference_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, preference_key)
);
"""

_CREATE_DESCRIPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS {schema}.schema_descriptions (
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255) NOT NULL DEFAULT '__table__',
    description TEXT NOT NULL,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (table_name, column_name)
);
"""


class PersistentMemory:
    """PostgreSQL-backed store for preferences and schema descriptions."""

    def __init__(self) -> None:
        settings = get_settings()
        self._dsn = settings.db.database_url
        self._schema = settings.db.metadata_schema
        self._ensure_tables()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def _ensure_tables(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(_CREATE_PREFERENCES_SQL.format(schema=self._schema))
            cur.execute(_CREATE_DESCRIPTIONS_SQL.format(schema=self._schema))
            conn.commit()

    # --- User preferences -------------------------------------------------

    def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Return preferences for ``user_id``, merged over defaults."""
        prefs = dict(DEFAULT_PREFERENCES)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT preference_key, preference_value "
                f"FROM {self._schema}.user_preferences WHERE user_id = %s",
                (user_id,),
            )
            for row in cur.fetchall():
                prefs[row["preference_key"]] = row["preference_value"]
        return prefs

    def set_user_preference(self, user_id: str, key: str, value: Any) -> None:
        """Upsert a single preference for ``user_id``."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self._schema}.user_preferences
                    (user_id, preference_key, preference_value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, preference_key) DO UPDATE
                SET preference_value = EXCLUDED.preference_value,
                    updated_at       = NOW()
                """,
                (user_id, key, Jsonb(value)),
            )
            conn.commit()

    # --- Schema descriptions ---------------------------------------------

    def get_schema_descriptions(
        self, table_name: str | None = None
    ) -> dict[str, dict[str, str]]:
        """Return approved schema descriptions.

        Shape: ``{table_name: {"__table__": "...", "column_a": "...", ...}}``.
        If ``table_name`` is given, returns only that table's entry.
        """
        sql = (
            f"SELECT table_name, column_name, description "
            f"FROM {self._schema}.schema_descriptions"
        )
        params: tuple = ()
        if table_name is not None:
            sql += " WHERE table_name = %s"
            params = (table_name,)

        result: dict[str, dict[str, str]] = {}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                tbl = row["table_name"]
                result.setdefault(tbl, {})[row["column_name"]] = row["description"]
        return result

    def save_schema_descriptions(
        self,
        descriptions: dict[str, dict[str, str]],
        approved_by: str,
    ) -> None:
        """Upsert a batch of descriptions.

        ``descriptions`` has shape ``{table_name: {"__table__": "...", "col": "..."}}``.
        """
        rows: list[tuple[str, str, str, str]] = []
        for table_name, cols in descriptions.items():
            for column_name, description in cols.items():
                rows.append((table_name, column_name, description, approved_by))

        if not rows:
            return

        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {self._schema}.schema_descriptions
                    (table_name, column_name, description, approved_by, approved_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (table_name, column_name) DO UPDATE
                SET description  = EXCLUDED.description,
                    approved_by  = EXCLUDED.approved_by,
                    approved_at  = NOW()
                """,
                rows,
            )
            conn.commit()
