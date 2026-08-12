"""L1 three-layer contract tests (GAP-05, P0).

The canonical L1 contract is defined by FOUR artifacts that must agree
field-for-field:

1. ``src/vencertia/benchmark/l1.py::L1Case``  (Python model)
2. ``schemas/historical_decision_case.schema.json``  (JSON Schema)
3. ``data/templates/historical_case_template.json``  (template)
4. ``data/benchmarks/l1_cases.jsonl``  (frozen benchmark cases)

Backward compatibility: old cases missing ``claims_at_t0`` / ``beliefs_at_t0`` /
``evidence_at_t0`` default to ``[]`` and are NEVER backfilled from
``future_outcome`` / ``hindsight_data`` (that would be leakage, ADR-006).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from vencertia.benchmark.l1 import L1Case, L1Runner


@pytest.fixture
def l1_schema(project_root: Path) -> dict:
    path = project_root / "schemas" / "historical_decision_case.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def l1_validator(l1_schema: dict) -> Draft7Validator:
    return Draft7Validator(l1_schema)


@pytest.fixture
def l1_template(project_root: Path) -> dict:
    path = project_root / "data" / "templates" / "historical_case_template.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _l1_cases(project_root: Path) -> list[dict]:
    path = project_root / "data" / "benchmarks" / "l1_cases.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Template → Schema → model_validate → L1Runner full chain
# ---------------------------------------------------------------------------


def test_template_matches_schema(l1_validator: Draft7Validator, l1_template: dict) -> None:
    errors = list(l1_validator.iter_errors(l1_template))
    assert errors == [], [e.message for e in errors]


def test_template_validates_through_l1_case_model(l1_template: dict) -> None:
    case = L1Case.model_validate(l1_template)
    assert case.id == l1_template["id"]
    assert case.domain == l1_template["domain"]
    # Canonical T0 three fields present.
    assert case.claims_at_t0 and case.beliefs_at_t0 and case.evidence_at_t0
    # Gold naming compatibility: gold_decision maps onto reference_option_id.
    assert case.gold_decision == "commit_mvp"
    assert case.reference_option_id == "commit_mvp"
    # Decision/options mirrors are populated from the envelope.
    assert case.decision is not None
    assert {o["id"] for o in case.options or []} == {"commit_mvp", "stop_project"}


def test_template_runs_through_l1_runner(
    project_root: Path, l1_template: dict
) -> None:
    """Template → L1Runner full chain must execute (not reject) the case."""
    runner = L1Runner()
    tmp_jsonl = project_root / "data" / "templates" / "_tmp_template_run.jsonl"
    try:
        tmp_jsonl.write_text(json.dumps(l1_template) + "\n", encoding="utf-8")
        report = runner.run(tmp_jsonl)
    finally:
        if tmp_jsonl.exists():
            tmp_jsonl.unlink()
    assert report.rejected == []
    assert any(c.id == l1_template["id"] for c in report.cases)


# ---------------------------------------------------------------------------
# l1_cases.jsonl three-layer pass
# ---------------------------------------------------------------------------


def test_all_l1_cases_pass_three_layers(
    project_root: Path, l1_validator: Draft7Validator
) -> None:
    cases = _l1_cases(project_root)
    assert len(cases) >= 7
    for raw in cases:
        errors = list(l1_validator.iter_errors(raw))
        assert errors == [], f"{raw.get('id')}: {[e.message for e in errors]}"
        L1Case.model_validate(raw)


def test_l1_runner_rejects_leakage_case(project_root: Path) -> None:
    """leakage_audit_passed != true ⇒ case is refused for formal L1 benchmark."""
    runner = L1Runner()
    report = runner.run(project_root / "data/benchmarks/l1_cases.jsonl")
    assert "l1-07-leak" in report.rejected
    assert all(c.id != "l1-07-leak" for c in report.cases)
    assert report.n == len(_l1_cases(project_root)) - 1


def test_leakage_gate_rejects_missing_audit_flag(project_root: Path) -> None:
    """A case that simply omits leakage_audit_passed is refused (no defaulting)."""
    raw = _l1_cases(project_root)[0].copy()
    raw["id"] = "l1-synthetic-no-audit"
    raw.pop("leakage_audit_passed", None)
    runner = L1Runner()
    tmp_jsonl = project_root / "data" / "benchmarks" / "_tmp_leak_gate.jsonl"
    try:
        tmp_jsonl.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        report = runner.run(tmp_jsonl)
    finally:
        if tmp_jsonl.exists():
            tmp_jsonl.unlink()
    assert "l1-synthetic-no-audit" in report.rejected
    assert report.cases == []


def test_leakage_gate_rejects_explicit_false_audit(project_root: Path) -> None:
    raw = _l1_cases(project_root)[0].copy()
    raw["id"] = "l1-synthetic-false-audit"
    raw["leakage_audit_passed"] = False
    runner = L1Runner()
    tmp_jsonl = project_root / "data" / "benchmarks" / "_tmp_leak_gate_false.jsonl"
    try:
        tmp_jsonl.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        report = runner.run(tmp_jsonl)
    finally:
        if tmp_jsonl.exists():
            tmp_jsonl.unlink()
    assert "l1-synthetic-false-audit" in report.rejected


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_legacy_case_without_t0_three_fields_defaults_to_empty(
    project_root: Path, l1_validator: Draft7Validator
) -> None:
    """Old cases missing claims_at_t0/beliefs_at_t0/evidence_at_t0 → []."""
    raw = _l1_cases(project_root)[0].copy()
    for key in ("claims_at_t0", "beliefs_at_t0", "evidence_at_t0", "decision", "options", "gold_decision", "actual_decision", "metadata"):
        raw.pop(key, None)
    # Schema must accept the legacy shape.
    errors = list(l1_validator.iter_errors(raw))
    assert errors == [], [e.message for e in errors]
    case = L1Case.model_validate(raw)
    assert case.claims_at_t0 == []
    assert case.beliefs_at_t0 == []
    assert case.evidence_at_t0 == []
    assert case.metadata == {}
    # The envelope decision is mirrored, never fabricated from hindsight.
    assert case.decision is not None


def test_legacy_case_never_backfills_from_hindsight() -> None:
    """T0 three fields must NOT be derived from future_outcome/hindsight_data."""
    raw = {
        "id": "legacy-no-backfill",
        "domain": "b2b-saas",
        "decision_time": "2026-01-01T00:00:00+00:00",
        "information_available_at_t0": {
            "decision": {
                "id": "D",
                "decision_question": "q",
                "objective_id": "O",
                "project_id": "P",
                "options": [],
                "relevant_belief_ids": [],
            },
            "beliefs": [],
            "evidence": [],
            "experiments": [],
        },
        "future_outcome": "SUCCESS",
        "hindsight_data": {"outcome": "mvp shipped, 3 customers paid"},
        "leakage_audit_passed": True,
    }
    case = L1Case.model_validate(raw)
    assert case.claims_at_t0 == []
    assert case.beliefs_at_t0 == []
    assert case.evidence_at_t0 == []
    # hindsight/future_outcome remain untouched and never leak into T0 slices.
    assert case.hindsight_data == {"outcome": "mvp shipped, 3 customers paid"}
    assert case.future_outcome == "SUCCESS"


def test_gold_decision_naming_compat() -> None:
    raw = {
        "id": "gold-naming",
        "decision_time": "2026-01-01T00:00:00Z",
        "information_available_at_t0": {
            "decision": {"id": "D", "options": [], "relevant_belief_ids": []},
            "beliefs": [],
            "evidence": [],
            "experiments": [],
        },
        "leakage_audit_passed": True,
        "gold_decision": "go",
    }
    case = L1Case.model_validate(raw)
    assert case.gold_decision == "go"
    assert case.reference_option_id == "go"


def test_gold_decision_conflict_with_reference_option_id_raises() -> None:
    raw = {
        "id": "gold-conflict",
        "decision_time": "2026-01-01T00:00:00Z",
        "information_available_at_t0": {
            "decision": {"id": "D", "options": [], "relevant_belief_ids": []},
            "beliefs": [],
            "evidence": [],
            "experiments": [],
        },
        "leakage_audit_passed": True,
        "gold_decision": "go",
        "reference_option_id": "stop",
    }
    with pytest.raises(ValueError):
        L1Case.model_validate(raw)


def test_actual_decision_is_informational_and_never_scored(project_root: Path) -> None:
    """actual_decision records what happened; only gold/reference drives scoring."""
    raw = _l1_cases(project_root)[0].copy()
    raw["actual_decision"] = "stop_project"  # historically they stopped, gold says commit
    case = L1Case.model_validate(raw)
    assert case.actual_decision == "stop_project"
    assert case.reference_option_id == raw["reference_option_id"]
