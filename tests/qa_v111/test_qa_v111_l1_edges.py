"""QA v1.1.1 Iteration 2 — adversarial edge cases for L1 contract + leakage.

Targets (QA task list):
  7. L1 old-case compat: only information_available_at_t0 → T0 three fields default []
  8. L1 future leakage: leakage_audit_passed=false rejected; T0 future info gate
"""

from __future__ import annotations

import json

from vencertia.benchmark.l1 import L1Case, L1Runner


def _old_style_case() -> dict:
    """A pre-GAP-05 case with ONLY information_available_at_t0 (no T0 slices)."""
    return {
        "id": "l1-old-01",
        "domain": "general",
        "decision_time": "2026-01-15T10:00:00Z",
        "information_available_at_t0": {
            "decision": {
                "id": "DEC_OLD",
                "decision_question": "q",
                "objective_id": "OBJ_1",
                "project_id": "PRJ_1",
                "options": [
                    {"id": "opt_a", "label": "A", "base_utility": 0.9,
                     "belief_coefficients": {"b1": 0.1}, "irreversible_cost": 0.0},
                    {"id": "opt_b", "label": "B", "base_utility": 0.3,
                     "belief_coefficients": {"b1": -0.1}, "irreversible_cost": 0.0},
                ],
                "relevant_belief_ids": ["b1"],
            },
            "beliefs": [
                {"id": "b1", "claim_id": "CLM_1", "statement": "belief", "scope": "PROJECT",
                 "probability": 0.7, "posterior": 0.7, "alpha": 2.0, "beta": 1.0,
                 "uncertainty": 0.2, "decision_relevant": True}
            ],
            "evidence": [],
            "experiments": [],
        },
        "gold_decision": "opt_a",
        "leakage_audit_passed": True,
    }


def test_old_case_defaults_t0_three_fields_to_empty():
    """Old case without claims_at_t0/beliefs_at_t0/evidence_at_t0 → default []."""
    case = L1Case.model_validate(_old_style_case())
    assert case.claims_at_t0 == []
    assert case.beliefs_at_t0 == []
    assert case.evidence_at_t0 == []
    # Mirrors still expose decision/options from the envelope.
    assert case.decision is not None
    assert len(case.options or []) == 2


def test_old_case_runs_through_runner():
    """Backward compat: the old-style case is accepted by the runner."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old_cases.jsonl"
        path.write_text(json.dumps(_old_style_case()) + "\n", encoding="utf-8")
        report = L1Runner().run(path)
        assert report.n == 1
        assert report.rejected == []


def test_leakage_audit_false_is_rejected():
    """leakage_audit_passed=false → case rejected outright (never replayed)."""
    raw = _old_style_case()
    raw["id"] = "l1-leak-01"
    raw["leakage_audit_passed"] = False
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "leak_cases.jsonl"
        path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        report = L1Runner().run(path)
        assert report.n == 0
        assert report.rejected == ["l1-leak-01"]


def test_leakage_flag_is_authoring_time_audit_not_runtime_scan():
    """DOCUMENTED BOUNDARY: the leakage gate is flag-based (ADR-006
    authoring-time audit). A case with leakage_audit_passed=True whose T0
    envelope happens to contain future-looking data is NOT detected by a
    runtime content scan — it runs. This matches the documented contract
    (audit happens at case-authoring time), not a runtime guard."""
    raw = _old_style_case()
    raw["id"] = "l1-future-look-01"
    # Simulate T0 evidence text that references a future date (would be a
    # human-audit failure, but the flag was wrongly set to True).
    raw["information_available_at_t0"]["evidence"] = [
        {
            "id": "E_FUT",
            "claim_ids": ["CLM_1"],
            "scope": "MARKET",
            "evidence_type": "REVIEWED_EXTERNAL_RESEARCH",
            "source": "By 2027 the market will triple",
            "directness": 0.6, "reliability": 0.6, "relevance": 0.6,
            "strength": 0.5, "supports_or_contradicts": "SUPPORTS",
            "authority_level": "REVIEWED_EXTERNAL_RESEARCH",
            "verification": "ESTIMATED",
        }
    ]
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "future_look.jsonl"
        path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        report = L1Runner().run(path)
        assert report.n == 1  # runs because flag is True (gate is flag-based)
