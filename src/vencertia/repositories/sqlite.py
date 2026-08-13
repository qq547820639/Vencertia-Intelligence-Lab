"""SQLite repository — full CRUD with optimistic locking and transactions."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    """SQLite-backed repository (stdlib sqlite3, full feature set).

    ``check_same_thread=False`` allows the FastAPI/uvicorn worker threads to
    share the connection created at startup (BLOCKER-API-001). The repository
    is used synchronously per request; no concurrent write from two threads
    happens inside a single request handler.
    """

    def __init__(self, dsn: str | None = None, path: str | Path | None = None) -> None:
        if path is not None:
            self.dsn = f"sqlite:///{path}"
        else:
            self.dsn = dsn if dsn is not None else "sqlite:///data/vencertia.db"
        db_path = parse_sqlite_dsn(self.dsn)
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        run_migrations(self.conn, "sqlite")
        self._closed = False

    # -- lifecycle (v1.9) ------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        if not getattr(self, "_closed", False):
            self.conn.close()
            self._closed = True

    def __enter__(self) -> SQLiteRepository:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _maybe_commit(self) -> None:
        """Commit only when not inside an outer transaction (P2-17).

        ``in_transaction`` increments ``_txn_depth``; while it is > 0 the
        backend connection is inside an explicit BEGIN and intermediate
        commits would destroy batch atomicity. The outermost frame commits.
        """
        if getattr(self, "_txn_depth", 0) == 0:
            self.conn.commit()

    def _rollback_implicit(self) -> None:
        """Roll back the driver's implicit transaction on a loud failure path
        (stale write / create-version mismatch). Inside an explicit batch
        (``in_transaction``, depth > 0) the outer ``_txn`` owns rollback."""
        if getattr(self, "_txn_depth", 0) == 0:
            self.conn.rollback()

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
                    # v1.9: parity with InMemoryRepository — creating a NEW row
                    # through the optimistic-lock path requires version 1.
                    if expected_version != 1:
                        self._rollback_implicit()
                        raise StaleWriteError(entity_type, obj.id, expected_version)
                    self.conn.execute(
                        "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                        "VALUES(?,?,?,?,?)",
                        (entity_type, obj.id, payload, obj.version, now),
                    )
                else:
                    # v1.9: a stale write must not commit the implicit
                    # transaction it opened (previously _maybe_commit()).
                    self._rollback_implicit()
                    raise StaleWriteError(entity_type, obj.id, expected_version)
        else:
            self.conn.execute(
                "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(entity_type,id) DO UPDATE SET "
                "payload=excluded.payload, version=excluded.version, updated_at=excluded.updated_at",
                (entity_type, obj.id, payload, obj.version, now),
            )
        self._maybe_commit()

    def _list_all(self, entity_type: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload FROM entities WHERE entity_type=?", (entity_type,)
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def _delete(self, entity_type: str, entity_id: str) -> None:
        self.conn.execute(
            "DELETE FROM entities WHERE entity_type=? AND id=?", (entity_type, entity_id)
        )
        self._maybe_commit()

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
        self._maybe_commit()
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

    # -- v1.1 special tables (hot paths) ----------------------------------------

    def save_binding(
        self, binding, expected_version: int | None = None
    ) -> None:
        payload = binding.model_dump_json()
        if expected_version is not None:
            cursor = self.conn.execute(
                "UPDATE claim_bindings SET claim_id=?, binding_confidence=?, binding_method=?, "
                "status=?, model=?, provider=?, matched_at=?, retry_count=?, version=?, payload=? "
                "WHERE id=? AND version=?",
                (
                    binding.claim_id,
                    binding.binding_confidence,
                    binding.binding_method.value
                    if hasattr(binding.binding_method, "value")
                    else str(binding.binding_method),
                    binding.status.value if hasattr(binding.status, "value") else str(binding.status),
                    binding.model,
                    binding.provider,
                    binding.matched_at.isoformat(),
                    binding.retry_count,
                    binding.version,
                    payload,
                    binding.id,
                    expected_version,
                ),
            )
            if cursor.rowcount == 0:
                existing = self.conn.execute(
                    "SELECT version FROM claim_bindings WHERE id=?", (binding.id,)
                ).fetchone()
                if existing is None:
                    if expected_version != 1:
                        self._rollback_implicit()
                        raise StaleWriteError("binding", binding.id, expected_version)
                    self.conn.execute(
                        "INSERT INTO claim_bindings(id,evidence_id,claim_id,binding_confidence,"
                        "binding_method,status,model,provider,matched_at,retry_count,version,payload) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            binding.id,
                            binding.evidence_id,
                            binding.claim_id,
                            binding.binding_confidence,
                            binding.binding_method.value
                            if hasattr(binding.binding_method, "value")
                            else str(binding.binding_method),
                            binding.status.value
                            if hasattr(binding.status, "value")
                            else str(binding.status),
                            binding.model,
                            binding.provider,
                            binding.matched_at.isoformat(),
                            binding.retry_count,
                            binding.version,
                            payload,
                        ),
                    )
                else:
                    self._rollback_implicit()
                    raise StaleWriteError("binding", binding.id, expected_version)
        else:
            self.conn.execute(
                "INSERT INTO claim_bindings(id,evidence_id,claim_id,binding_confidence,"
                "binding_method,status,model,provider,matched_at,retry_count,version,payload) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "claim_id=excluded.claim_id, binding_confidence=excluded.binding_confidence, "
                "binding_method=excluded.binding_method, status=excluded.status, "
                "model=excluded.model, provider=excluded.provider, matched_at=excluded.matched_at, "
                "retry_count=excluded.retry_count, version=excluded.version, payload=excluded.payload",
                (
                    binding.id,
                    binding.evidence_id,
                    binding.claim_id,
                    binding.binding_confidence,
                    binding.binding_method.value
                    if hasattr(binding.binding_method, "value")
                    else str(binding.binding_method),
                    binding.status.value if hasattr(binding.status, "value") else str(binding.status),
                    binding.model,
                    binding.provider,
                    binding.matched_at.isoformat(),
                    binding.retry_count,
                    binding.version,
                    payload,
                ),
            )
        self._maybe_commit()

    def get_binding(self, binding_id: str):
        row = self.conn.execute(
            "SELECT payload FROM claim_bindings WHERE id=?", (binding_id,)
        ).fetchone()
        if row is None:
            return None
        from vencertia.domain import EvidenceClaimBinding

        return EvidenceClaimBinding.model_validate_json(row["payload"])

    def list_bindings(
        self,
        evidence_id: str | None = None,
        claim_id: str | None = None,
        status: str | None = None,
    ) -> list:
        sql = "SELECT payload FROM claim_bindings WHERE 1=1"
        params: list[Any] = []
        if evidence_id is not None:
            sql += " AND evidence_id=?"
            params.append(evidence_id)
        if claim_id is not None:
            sql += " AND claim_id=?"
            params.append(claim_id)
        if status is not None:
            sql += " AND status=?"
            params.append(status)
        rows = self.conn.execute(sql, params).fetchall()
        from vencertia.domain import EvidenceClaimBinding

        return [EvidenceClaimBinding.model_validate_json(r["payload"]) for r in rows]

    def save_belief_update_record(self, record) -> None:
        payload = record.model_dump_json()
        self.conn.execute(
            "INSERT INTO belief_update_records(id,belief_id,claim_id,posterior_version,"
            "created_at,payload) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "belief_id=excluded.belief_id, claim_id=excluded.claim_id, "
            "posterior_version=excluded.posterior_version, created_at=excluded.created_at, "
            "payload=excluded.payload",
            (
                record.id,
                record.belief_id,
                record.claim_id,
                record.posterior_version,
                record.created_at.isoformat(),
                payload,
            ),
        )
        self._maybe_commit()

    def list_belief_update_records(self, belief_id: str) -> list:
        rows = self.conn.execute(
            "SELECT payload FROM belief_update_records WHERE belief_id=? ORDER BY posterior_version",
            (belief_id,),
        ).fetchall()
        from vencertia.domain import BeliefUpdateRecord

        return [BeliefUpdateRecord.model_validate_json(r["payload"]) for r in rows]
