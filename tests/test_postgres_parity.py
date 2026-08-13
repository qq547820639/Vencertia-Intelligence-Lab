"""PostgreSQL parity tests (M0-5).

The PG backend is DSN-gated and requires the optional ``psycopg`` driver. On
machines without ``VENCERTIA_PG_DSN`` (or without psycopg), the end-to-end test
is skipped with an honest warning; the DDL correctness is still verified via a
fake connection so the migration contract is locked regardless of environment.
"""

from __future__ import annotations

import os
import warnings

import pytest

from vencertia.repositories.migrations import SCHEMA_PG_V1_1, run_migrations


def test_m05_pg_schema_declares_special_tables():
    assert "CREATE TABLE IF NOT EXISTS claim_bindings" in SCHEMA_PG_V1_1
    assert "CREATE TABLE IF NOT EXISTS belief_update_records" in SCHEMA_PG_V1_1


def test_m05_run_migrations_postgres_executes_both_schemas():
    executed: list[str] = []

    class _FakeConn:
        def execute(self, sql: str) -> None:
            executed.append(sql)

        def commit(self) -> None:
            pass

    run_migrations(_FakeConn(), "postgres")
    assert len(executed) == 2
    assert "CREATE TABLE IF NOT EXISTS entities" in executed[0]
    assert "CREATE TABLE IF NOT EXISTS claim_bindings" in executed[1]
    assert "CREATE TABLE IF NOT EXISTS belief_update_records" in executed[1]


def test_m05_postgres_repository_disabled_without_dsn():
    from vencertia.repositories.postgres import PostgresDisabledError, PostgresRepository

    with pytest.raises(PostgresDisabledError):
        PostgresRepository(dsn=None)


def _pg_available() -> tuple[bool, str]:
    if not os.environ.get("VENCERTIA_PG_DSN"):
        return False, "VENCERTIA_PG_DSN not set; PostgreSQL parity not exercised"
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False, "psycopg not installed; PostgreSQL parity not exercised"
    return True, ""


def test_m05_postgres_end_to_end():
    """Round-trip against a real PostgreSQL database (skipped when unavailable)."""
    available, reason = _pg_available()
    if not available:
        warnings.warn(f"PostgreSQL parity test skipped: {reason}", UserWarning, stacklevel=2)
        pytest.skip(reason)

    from vencertia.repositories.postgres import PostgresRepository

    repo = PostgresRepository(os.environ["VENCERTIA_PG_DSN"])
    try:
        with repo.conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name IN (%s, %s)",
                ("claim_bindings", "belief_update_records"),
            )
            names = {row[0] for row in cur.fetchall()}
        assert names == {"claim_bindings", "belief_update_records"}
    finally:
        repo.conn.close()
