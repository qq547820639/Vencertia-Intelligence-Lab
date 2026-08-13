"""CallRecorder — provider observability (v1.1).

Wraps provider calls and records a :class:`ProviderCallRecord` via the
repository. Red line (ADR-012): the record NEVER contains prompt text or other
sensitive content — only metadata (provider/model/request_id/latency/tokens/
cost/success/retry).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import ProviderCallRecord, utcnow
from vencertia.repositories.base import Repository


class CallRecorder:
    """Records ProviderCallRecord for model/search/retrieval/research calls."""

    def __init__(
        self,
        repo: Repository,
        enabled: bool = True,
        settings: Settings | None = None,
    ) -> None:
        self.repo = repo
        self.enabled = enabled
        self.settings = settings or get_settings()

    def record(
        self,
        kind: str,
        provider: str,
        model: str,
        task_kind: str,
        fn: Callable[[], Any],
        request_id: str = "",
        retry_count: int | Callable[[], int] = 0,
        tokens: dict | None = None,
        cost: float = 0.0,
    ) -> Any:
        """Execute ``fn`` and record the outcome (structured errors included).

        ``retry_count`` may be a callable so wrappers can report the ACTUAL
        number of attempts after the call completes (resilience wrappers).
        ``tokens``/``cost`` are metadata only; the record NEVER contains
        prompts or API keys (ADR-012 red line).
        """
        if not self.enabled:
            return fn()
        started = time.monotonic()
        started_at = utcnow()
        success = True
        error_type: str | None = None
        result: Any = None
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - record any provider failure
            success = False
            error_type = getattr(exc, "error_type", type(exc).__name__)
            raise
        finally:
            latency_ms = round((time.monotonic() - started) * 1000.0, 3)
            retries = retry_count() if callable(retry_count) else retry_count
            record = ProviderCallRecord(
                id="PCR_" + uuid4().hex,
                kind=kind,
                provider=provider,
                model=model,
                request_id=request_id or "req_" + uuid4().hex,
                task_kind=task_kind,
                started_at=started_at,
                latency_ms=latency_ms,
                tokens=tokens or {},
                cost=round(float(cost), 6),
                success=success,
                retry_count=retries,
                error_type=error_type,
            )
            with suppress(Exception):  # pragma: no cover - audit must never block
                self.repo.save_call_record(record)
        return result

    def wrap(
        self,
        fn: Callable,
        kind: str,
        provider: str,
        model: str,
        task_kind: str,
    ) -> Callable:
        """Return a wrapped callable that records on invocation."""

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            return self.record(kind, provider, model, task_kind, lambda: fn(*args, **kwargs))

        return _wrapped
