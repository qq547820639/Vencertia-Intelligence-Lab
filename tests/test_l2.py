"""L2 prospective prediction runner tests (v1.1)."""

from __future__ import annotations

from datetime import timedelta

from vencertia.benchmark.l2 import L2Runner
from vencertia.domain import PredictionEntry, utcnow
from vencertia.repositories.memory import InMemoryRepository


def _entry(pid, due_days=5) -> PredictionEntry:
    return PredictionEntry(
        id=pid,
        project_id="PRJ_L2",
        claim_id="CLM_X",
        target="target",
        predicted_probability=0.6,
        due_at=utcnow() + timedelta(days=due_days),
    )


def test_register_then_settle(tmp_path):
    repo = InMemoryRepository()
    runner = L2Runner(repo=repo, path=tmp_path / "predictions.jsonl")
    runner.register(_entry("PRD_L2_1"))
    assert repo.get_prediction("PRD_L2_1") is not None
    settled = runner.settle("PRD_L2_1", True, "user_alice")
    assert settled.resolution == "TRUE"
    assert settled.outcome is True
    assert settled.predicted_probability == 0.6  # immutable
    assert settled.resolution_source == "user_alice"


def test_due_report_lists_overdue(tmp_path):
    repo = InMemoryRepository()
    runner = L2Runner(repo=repo, path=tmp_path / "predictions.jsonl")
    runner.register(_entry("PRD_DUE", due_days=-1))
    runner.register(_entry("PRD_FUTURE", due_days=30))
    due = runner.due_report()
    ids = {p.id for p in due}
    assert "PRD_DUE" in ids
    assert "PRD_FUTURE" not in ids


def test_cannot_settle_twice(tmp_path):
    repo = InMemoryRepository()
    runner = L2Runner(repo=repo, path=tmp_path / "predictions.jsonl")
    runner.register(_entry("PRD_L2_2"))
    runner.settle("PRD_L2_2", False, "user")
    import pytest

    with pytest.raises(ValueError):
        runner.settle("PRD_L2_2", True, "user")


def test_register_writes_schema_file(tmp_path):
    repo = InMemoryRepository()
    runner = L2Runner(repo=repo, path=tmp_path / "predictions.jsonl")
    runner.register(_entry("PRD_L2_3"))
    lines = (tmp_path / "predictions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json

    payload = json.loads(lines[0])
    for field in (
        "id",
        "project_id",
        "claim_id",
        "target",
        "predicted_probability",
        "registered_at",
        "due_at",
    ):
        assert field in payload
