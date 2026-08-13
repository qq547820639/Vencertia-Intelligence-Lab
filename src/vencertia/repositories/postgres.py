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
        self._closed = False

    # -- lifecycle (v1.9) ------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        if not getattr(self, "_closed", False):
            self.conn.close()
            self._closed = True

    def __enter__(self) -> PostgresRepository:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _maybe_commit(self) -> None:
        """Commit only when not inside an outer transaction (P2-17).

        psycopg3's ``with conn.transaction()`` owns the outermost commit;
        intermediate commits inside a batch would break atomicity.
        """
        if getattr(self, "_txn_depth", 0) == 0:
            self.conn.commit()

    def _rollback_implicit(self) -> None:
        """Close the implicit transaction before a loud failure path (stale
        write / create-version mismatch). Inside an explicit batch
        (``in_transaction``, depth > 0) the outer ``conn.transaction()``
        context manager owns the rollback."""
        if getattr(self, "_txn_depth", 0) == 0:
            self.conn.rollback()

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
                        # v1.9: parity with InMemoryRepository — creating a NEW
                        # row through the optimistic-lock path requires version 1.
                        if expected_version != 1:
                            self._rollback_implicit()
                            raise StaleWriteError(entity_type, obj.id, expected_version)
                        cur.execute(
                            "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                            "VALUES(%s,%s,%s,%s,%s)",
                            (entity_type, obj.id, payload, obj.version, now),
                        )
                    else:
                        # v1.9: close the implicit transaction before raising —
                        # previously this left the connection "in transaction".
                        self._rollback_implicit()
                        raise StaleWriteError(entity_type, obj.id, expected_version)
            else:
                cur.execute(
                    "INSERT INTO entities(entity_type,id,payload,version,updated_at) "
                    "VALUES(%s,%s,%s,%s,%s) "
                    "ON CONFLICT(entity_type,id) DO UPDATE SET "
                    "payload=EXCLUDED.payload, version=EXCLUDED.version, updated_at=EXCLUDED.updated_at",
                    (entity_type, obj.id, payload, obj.version, now),
                )
        self._maybe_commit()

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
        self._maybe_commit()

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
        self._maybe_commit()
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

    # -- v1.1 special tables (hot paths, PG dialect) ---------------------------
    # Mirrors SQLiteRepository's claim_bindings / belief_update_records overrides
    # against the PostgreSQL-specific 0004_pg_v1_1.sql schema.

    @staticmethod
    def _binding_method(binding) -> str:
        return (
            binding.binding_method.value
            if hasattr(binding.binding_method, "value")
            else str(binding.binding_method)
        )

    @staticmethod
    def _binding_status(binding) -> str:
        return binding.status.value if hasattr(binding.status, "value") else str(binding.status)

    def save_binding(self, binding, expected_version: int | None = None) -> None:
        payload = json.loads(binding.model_dump_json())
        params = (
            binding.id,
            binding.evidence_id,
            binding.claim_id,
            binding.binding_confidence,
            self._binding_method(binding),
            self._binding_status(binding),
            binding.model,
            binding.provider,
            binding.matched_at,
            binding.retry_count,
            binding.version,
            payload,
        )
        with self.conn.cursor() as cur:
            if expected_version is not None:
                cur.execute(
                    "UPDATE claim_bindings SET claim_id=%s, binding_confidence=%s, "
                    "binding_method=%s, status=%s, model=%s, provider=%s, matched_at=%s, "
                    "retry_count=%s, version=%s, payload=%s WHERE id=%s AND version=%s",
                    (
                        binding.claim_id,
                        binding.binding_confidence,
                        self._binding_method(binding),
                        self._binding_status(binding),
                        binding.model,
                        binding.provider,
                        binding.matched_at,
                        binding.retry_count,
                        binding.version,
                        payload,
                        binding.id,
                        expected_version,
                    ),
                )
                if cur.rowcount == 0:
                    cur.execute("SELECT version FROM claim_bindings WHERE id=%s", (binding.id,))
                    existing = cur.fetchone()
                    if existing is None:
                        if expected_version != 1:
                            self._rollback_implicit()
                            raise StaleWriteError("binding", binding.id, expected_version)
                        cur.execute(
                            "INSERT INTO claim_bindings(id,evidence_id,claim_id,binding_confidence,"
                            "binding_method,status,model,provider,matched_at,retry_count,version,payload) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            params,
                        )
                    else:
                        # v1.9: close the implicit transaction before raising
                        # (previously leaked an open transaction).
                        self._rollback_implicit()
                        raise StaleWriteError("binding", binding.id, expected_version)
            else:
                cur.execute(
                    "INSERT INTO claim_bindings(id,evidence_id,claim_id,binding_confidence,"
                    "binding_method,status,model,provider,matched_at,retry_count,version,payload) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "claim_id=EXCLUDED.claim_id, binding_confidence=EXCLUDED.binding_confidence, "
                    "binding_method=EXCLUDED.binding_method, status=EXCLUDED.status, "
                    "model=EXCLUDED.model, provider=EXCLUDED.provider, matched_at=EXCLUDED.matched_at, "
                    "retry_count=EXCLUDED.retry_count, version=EXCLUDED.version, payload=EXCLUDED.payload",
                    params,
                )
        self._maybe_commit()

    def get_binding(self, binding_id: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT payload FROM claim_bindings WHERE id=%s", (binding_id,))
            row = cur.fetchone()
        if row is None:
            return None
        from vencertia.domain import EvidenceClaimBinding

        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return EvidenceClaimBinding.model_validate(payload)

    def list_bindings(
        self,
        evidence_id: str | None = None,
        claim_id: str | None = None,
        status: str | None = None,
    ) -> list:
        sql = "SELECT payload FROM claim_bindings WHERE 1=1"
        params: list[Any] = []
        if evidence_id is not None:
            sql += " AND evidence_id=%s"
            params.append(evidence_id)
        if claim_id is not None:
            sql += " AND claim_id=%s"
            params.append(claim_id)
        if status is not None:
            sql += " AND status=%s"
            params.append(status)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        from vencertia.domain import EvidenceClaimBinding

        out: list = []
        for row in rows:
            payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            out.append(EvidenceClaimBinding.model_validate(payload))
        return out

    def save_belief_update_record(self, record) -> None:
        payload = json.loads(record.model_dump_json())
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO belief_update_records(id,belief_id,claim_id,posterior_version,"
                "created_at,payload) VALUES(%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET "
                "belief_id=EXCLUDED.belief_id, claim_id=EXCLUDED.claim_id, "
                "posterior_version=EXCLUDED.posterior_version, created_at=EXCLUDED.created_at, "
                "payload=EXCLUDED.payload",
                (
                    record.id,
                    record.belief_id,
                    record.claim_id,
                    record.posterior_version,
                    record.created_at,
                    payload,
                ),
            )
        self._maybe_commit()

    def list_belief_update_records(self, belief_id: str) -> list:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM belief_update_records WHERE belief_id=%s ORDER BY posterior_version",
                (belief_id,),
            )
            rows = cur.fetchall()
        from vencertia.domain import BeliefUpdateRecord

        out: list = []
        for row in rows:
            payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            out.append(BeliefUpdateRecord.model_validate(payload))
        return out
