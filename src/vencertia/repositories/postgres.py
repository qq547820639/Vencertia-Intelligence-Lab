"""PostgreSQL repository — same interface as SQLite, DSN-gated (ADR-005).

Instantiating without ``VENCERTIA_PG_DSN`` (or without the optional
``psycopg[binary]`` extra) raises :class:`PostgresDisabledError`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from vencertia.config import get_settings
from vencertia.domain.base import VencertiaBaseModel, utcnow
from vencertia.events.types import DomainEvent
from vencertia.repositories.base import EntityStoreMixin, PostgresDisabledError, StaleWriteError
from vencertia.repositories.migrations import run_migrations


class PostgresRepository(EntityStoreMixin):
    """PostgreSQL-backed repository (psycopg3)."""

    def __init__(self, dsn: str | None = None) -> None:
        resolved = dsn if dsn is not None else get_settings().postgres_dsn
        if not resolved:
            raise PostgresDisabledError(
                "PostgreSQL disabled: no VENCERTIA_PG_DSN configured. "
                "Set VENCERTIA_PG_DSN or use the SQLite backend."
            )
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise PostgresDisabledError(
                "psycopg is not installed. Install with: pip install 'vencertia-decision-runtime[postgres]'"
            ) from exc
        self.dsn = resolved
        self.conn = psycopg.connect(resolved)
        run_migrations(self.conn, "postgres")

    # -- primitives ----------------------------------------------------------

    def _load(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM entities WHERE entity_type=%s AND id=%s",
                (entity_type, entity_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def _store(
        self,
        entity_type: str,
        obj: VencertiaBaseModel,
        expected_version: int | None = None,
    ) -> None:
        payload = json.loads(obj.model_dump_json())
        now = utcnow()
        with self.conn.cursor() as cur:
            if expected_version is not None:
                cur.execute(
                    "UPDATE entities SET payload=%s, version=%s, updated_at=%s "
                    "WHERE entity_type=%s AND id=%s AND version=%s",
                    (payload, obj.version, now, entity_type, obj.id, expected_version),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "SELECT version FROM entities WHERE entity_type=%s AND id=%s",
                        (entity_type, obj.id),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        cur.execute(
                            "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                            "VALUES(%s,%s,%s,%s,%s)",
                            (entity_type, obj.id, payload, obj.version, now),
                        )
                    else:
                        raise StaleWriteError(entity_type, obj.id, expected_version)
            else:
                cur.execute(
                    "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                    "VALUES(%s,%s,%s,%s,%s) "
                    "ON CONFLICT(entity_type,id) DO UPDATE SET "
                    "payload=EXCLUDED.payload, version=EXCLUDED.version, updated_at=EXCLUDED.updated_at",
                    (entity_type, obj.id, payload, obj.version, now),
                )
        self.conn.commit()

    def _list_all(self, entity_type: str) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM entities WHERE entity_type=%s", (entity_type,)
            )
            rows = cur.fetchall()
        out = []
        for row in rows:
            out.append(row[0] if isinstance(row[0], dict) else json.loads(row[0]))
        return out

    def _delete(self, entity_type: str, entity_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM entities WHERE entity_type=%s AND id=%s",
                (entity_type, entity_id),
            )
        self.conn.commit()

    def _append_event(self, event: DomainEvent) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO event_log(event_id,event_type,entity_type,entity_id,payload,actor,occurred_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING seq",
                (
                    event.event_id,
                    event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                    event.entity_type,
                    event.entity_id,
                    json.loads(json.dumps(event.payload)),
                    event.actor,
                    event.occurred_at,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return int(row[0]) if row else 0

    def _events_since(self, after_seq: int) -> list[DomainEvent]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT seq,event_id,event_type,entity_type,entity_id,payload,actor,occurred_at "
                "FROM event_log WHERE seq>%s ORDER BY seq",
                (after_seq,),
            )
            rows = cur.fetchall()
        events: list[DomainEvent] = []
        for row in rows:
            # columns: seq, event_id, event_type, entity_type, entity_id, payload, actor, occurred_at
            payload = row[5] if isinstance(row[5], dict) else json.loads(row[5] or "{}")
            events.append(
                DomainEvent(
                    seq=row[0],
                    event_id=row[1],
                    event_type=row[2],
                    entity_type=row[3],
                    entity_id=row[4],
                    payload=payload,
                    actor=row[6],
                    occurred_at=row[7],
                )
            )
        return events

    def _txn(self, fn: Callable[[], None]) -> None:
        with self.conn.transaction():
            fn()
