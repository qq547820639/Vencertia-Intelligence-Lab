"""CallRecorder / ProviderCallRecord observability tests (v1.1)."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import ProviderCallRecord
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.observability import CallRecorder


def test_record_success():
    repo = InMemoryRepository()
    recorder = CallRecorder(repo, enabled=True, settings=Settings())
    result = recorder.record(
        "model", "mock", "mock", "compile", lambda: {"ok": True}, request_id="req_1"
    )
    assert result == {"ok": True}
    records = repo.list_call_records()
    assert len(records) == 1
    record = records[0]
    assert record.kind == "model"
    assert record.provider == "mock"
    assert record.request_id == "req_1"
    assert record.success is True
    assert record.latency_ms >= 0


def test_record_failure_marks_success_false_and_reraises():
    repo = InMemoryRepository()
    recorder = CallRecorder(repo, enabled=True, settings=Settings())

    def boom():
        raise ValueError("invalid json")

    import pytest

    with pytest.raises(ValueError):
        recorder.record("model", "mock", "mock", "compile", boom)
    records = repo.list_call_records()
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].error_type == "ValueError"


def test_record_never_contains_prompt():
    """Red line (ADR-012): records must not include prompt/sensitive content."""
    repo = InMemoryRepository()
    recorder = CallRecorder(repo, enabled=True, settings=Settings())
    recorder.record(
        "model", "mock", "mock", "compile",
        lambda: {"ok": True},
    )
    record = repo.list_call_records()[0]
    dumped = record.model_dump(mode="json")
    joined = str(dumped).lower()
    assert "prompt" not in joined
    assert "secret" not in joined
    assert "password" not in joined
    assert "api_key" not in joined


def test_wrap_decorator():
    repo = InMemoryRepository()
    recorder = CallRecorder(repo, enabled=True, settings=Settings())

    def search(query: str, k: int = 5):
        return [query] * k

    wrapped = recorder.wrap(search, kind="search", provider="mock", model="mock", task_kind="research_run")
    result = wrapped("q", k=2)
    assert result == ["q", "q"]
    records = repo.list_call_records()
    assert len(records) == 1
    assert records[0].kind == "search"
    assert records[0].task_kind == "research_run"


def test_disabled_recorder_records_nothing():
    repo = InMemoryRepository()
    recorder = CallRecorder(repo, enabled=False, settings=Settings())
    recorder.record("model", "mock", "mock", "compile", lambda: 42)
    assert repo.list_call_records() == []


def test_provider_call_record_contract():
    record = ProviderCallRecord(
        id="PCR_1", kind="model", provider="mock", model="mock",
        request_id="req_1", task_kind="compile",
    )
    assert record.success is True
    assert record.retry_count == 0
    assert record.tokens == {}
    assert record.cost == 0.0
