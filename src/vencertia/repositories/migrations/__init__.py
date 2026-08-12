"""SQLite migrations (idempotent DDL)."""

from __future__ import annotations

from pathlib import Path

SCHEMA_SQLITE = (Path(__file__).parent / "0001_initial.sql").read_text(encoding="utf-8")
SCHEMA_POSTGRES = (Path(__file__).parent / "0002_pg.sql").read_text(encoding="utf-8")


def run_migrations(conn, backend: str = "sqlite") -> None:
    """Execute idempotent DDL for the given backend on an open connection."""
    if backend == "postgres":
        conn.execute(SCHEMA_POSTGRES)
        conn.commit()
        return
    conn.executescript(SCHEMA_SQLITE)
    conn.commit()
