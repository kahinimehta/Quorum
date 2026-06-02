"""
Database connection layer — SQLite (local) or Supabase Postgres (team shared).

Set SUPABASE_DATABASE_URL or DATABASE_URL to the postgresql:// URI from
Supabase → Project Settings → Database → Connection string (URI).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from paths import default_db_path, schema_path


def database_url() -> str | None:
    return os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")


def is_postgres() -> bool:
    url = database_url() or ""
    return url.startswith("postgresql://") or url.startswith("postgres://")


def schema_file() -> str:
    if is_postgres():
        return os.path.join(os.path.dirname(schema_path()), "schema.pg.sql")
    return schema_path()


def _adapt_placeholders(sql: str) -> str:
    if is_postgres():
        return sql.replace("?", "%s")
    return sql


class DbConnection:
    """Thin wrapper so agents work on SQLite or Postgres."""

    def __init__(self, raw, *, postgres: bool):
        self._raw = raw
        self.postgres = postgres
        self._last_cursor = None

    def execute(self, sql: str, params: tuple | list = ()) -> "DbConnection":
        self._last_cursor = self._raw.execute(_adapt_placeholders(sql), params)
        return self

    def executescript(self, script: str) -> None:
        if self.postgres:
            for stmt in script.split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                self._raw.execute(stmt)
        else:
            self._raw.executescript(script)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()

    @property
    def rowcount(self) -> int:
        return self._last_cursor.rowcount if self._last_cursor else 0

    @property
    def lastrowid(self) -> int | None:
        if not self._last_cursor:
            return None
        if self.postgres:
            return None
        return self._last_cursor.lastrowid

    def fetchone(self) -> dict | None:
        if self._last_cursor is None:
            return None
        row = self._last_cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(row)

    def fetchall(self) -> list[dict]:
        if self._last_cursor is None:
            return []
        return [dict(r) if not isinstance(r, dict) else r for r in self._last_cursor.fetchall()]


def insert_ignore_sql(table: str, columns: list[str], conflict: list[str]) -> str:
    cols = ", ".join(columns)
    ph = ", ".join(["?"] * len(columns))
    if is_postgres():
        conflict_cols = ", ".join(conflict)
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )
    return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({ph})"


def truncate_all(conn: DbConnection) -> None:
    """Clear all tables (Postgres team DB rebuild)."""
    conn.execute("""
        TRUNCATE TABLE
            connection_evidence,
            subgroup_evidence,
            recommendations,
            agent_outputs,
            treatment_connections,
            evidence,
            subgroups,
            scan_state
        RESTART IDENTITY CASCADE
    """)
    conn.execute(
        "INSERT INTO scan_state (id, disease) VALUES (?, ?)",
        (1, "Parkinson disease"),
    )


@contextmanager
def connect(db_path: str | None = None) -> Iterator[DbConnection]:
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(database_url(), row_factory=dict_row)
        conn = DbConnection(raw, postgres=True)
        try:
            yield conn
        finally:
            conn.close()
    else:
        path = db_path or default_db_path()
        raw = sqlite3.connect(path)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        raw.execute("PRAGMA journal_mode = WAL")
        conn = DbConnection(raw, postgres=False)
        try:
            yield conn
        finally:
            conn.close()


def backend_label() -> str:
    if is_postgres():
        return "Supabase (PostgreSQL)"
    return default_db_path()
