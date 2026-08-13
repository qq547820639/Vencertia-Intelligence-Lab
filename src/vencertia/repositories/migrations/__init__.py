"""SQLite migrations (idempotent DDL)."""

from __future__ import annotations

from pathlib import Path

SCHEMA_SQLITE = (Path(__file__).parent / "0001_initial.sql").read_text(encoding="utf-8")
SCHEMA_POSTGRES = (Path(__file__).parent / "0002_pg.sql").read_text(encoding="utf-8")
SCHEMA_V1_1 = (Path(__file__).parent / "0003_v1_1.sql").read_text(encoding="utf-8")
SCHEMA_PG_V1_1 = (Path(__file__).parent / "0004_pg_v1_1.sql").read_text(encoding="utf-8")


def run_migrations(conn, backend: str = "sqlite") -> None:
    """Execute idempotent DDL for the given backend on an open connection."""
    if backend == "postgres":
        conn.execute(SCHEMA_POSTGRES)  # 0002 entities + event_log
        conn.execute(SCHEMA_PG_V1_1)  # 0004 v1.1 special tables (PG dialect)
        conn.commit()
        return
    conn.executescript(SCHEMA_SQLITE)
    conn.executescript(SCHEMA_V1_1)
    conn.commit()
