"""SQLite repository — full CRUD with optimistic locking and transactions."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable

from vencertia.domain.base import VencertiaBaseModel, utcnow
from vencertia.events.types import DomainEvent
from vencertia.repositories.base import EntityStoreMixin, StaleWriteError
from vencertia.repositories.migrations import run_migrations


def parse_sqlite_dsn(dsn: str) -> str:
    """Convert a ``sqlite:///...`` DSN into a filesystem path sqlite3 accepts.

    ``sqlite:///:memory:`` -> ``:memory:``; ``sqlite:///data/x.db`` -> ``data/x.db``.
    Plain paths are returned unchanged.
    """
    if dsn.startswith("sqlite:///"):
        return dsn[len("sqlite:///") :]
    if dsn.startswith("sqlite://"):
        return dsn[len("sqlite://") :]
    return dsn


class SQLiteRepository(EntityStoreMixin):
    """SQLite-backed repository (stdlib sqlite3, full feature set)."""

    def __init__(self, dsn: str | None = None, path: str | Path | None = None) -> None:
        if path is not None:
            self.dsn = f"sqlite:///{path}"
        else:
            self.dsn = dsn if dsn is not None else "sqlite:///data/vencertia.db"
        db_path = parse_sqlite_dsn(self.dsn)
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        run_migrations(self.conn, "sqlite")

    # -- primitives ----------------------------------------------------------

    def _load(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM entities WHERE entity_type=? AND id=?",
            (entity_type, entity_id),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def _store(
        self,
        entity_type: str,
        obj: VencertiaBaseModel,
        expected_version: int | None = None,
    ) -> None:
        payload = obj.model_dump_json()
        now = utcnow().isoformat()
        if expected_version is not None:
            cursor = self.conn.execute(
                "UPDATE entities SET payload=?, version=?, updated_at=? "
                "WHERE entity_type=? AND id=? AND version=?",
                (payload, obj.version, now, entity_type, obj.id, expected_version),
            )
            if cursor.rowcount == 0:
                existing = self.conn.execute(
                    "SELECT version FROM entities WHERE entity_type=? AND id=?",
                    (entity_type, obj.id),
                ).fetchone()
                if existing is None:
                    self.conn.execute(
                        "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                        "VALUES(?,?,?,?,?)",
                        (entity_type, obj.id, payload, obj.version, now),
                    )
                else:
                    self.conn.commit()
                    raise StaleWriteError(entity_type, obj.id, expected_version)
        else:
            self.conn.execute(
                "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(entity_type,id) DO UPDATE SET "
                "payload=excluded.payload, version=excluded.version, updated_at=excluded.updated_at",
                (entity_type, obj.id, payload, obj.version, now),
            )
        self.conn.commit()

    def _list_all(self, entity_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload FROM entities WHERE entity_type=?", (entity_type,)
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def _delete(self, entity_type: str, entity_id: str) -> None:
        self.conn.execute(
            "DELETE FROM entities WHERE entity_type=? AND id=?", (entity_type, entity_id)
        )
        self.conn.commit()

    def _append_event(self, event: DomainEvent) -> int:
        cursor = self.conn.execute(
            "INSERT INTO event_log(event_id,event_type,entity_type,entity_id,payload,actor,occurred_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                event.event_id,
                event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                event.entity_type,
                event.entity_id,
                json.dumps(event.payload),
                event.actor,
                event.occurred_at.isoformat(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _events_since(self, after_seq: int) -> list[DomainEvent]:
        rows = self.conn.execute(
            "SELECT seq,event_id,event_type,entity_type,entity_id,payload,actor,occurred_at "
            "FROM event_log WHERE seq>? ORDER BY seq",
            (after_seq,),
        ).fetchall()
        events: list[DomainEvent] = []
        for row in rows:
            events.append(
                DomainEvent(
                    seq=row["seq"],
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    payload=json.loads(row["payload"] or "{}"),
                    actor=row["actor"],
                    occurred_at=row["occurred_at"],
                )
            )
        return events

    def _txn(self, fn: Callable[[], None]) -> None:
        self.conn.execute("BEGIN")
        try:
            fn()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
