"""Evidence conflict tests (v1.1)."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Belief, Evidence
from vencertia.runtime.conflict_engine import ConflictEngine


def _evidence(eid, direction, strength=0.9, reliability=0.9) -> Evidence:
    return Evidence(
        id=eid, claim_ids=["CLM_X"], scope="PROJECT", evidence_type="OBSERVED_BEHAVIOR",
        source=eid, supports_or_contradicts=direction, strength=strength, reliability=reliability,
    )


def test_detect_conflict_when_both_sides_exceed_threshold():
    engine = ConflictEngine(Settings())
    conflicts = engine.detect(
        {"CLM_X": [_evidence("E_SUP", "SUPPORTS"), _evidence("E_CON", "CONTRADICTS")]},
        threshold=0.3,
    )
    assert len(conflicts) == 1
    assert conflicts[0].claim_id == "CLM_X"
    assert conflicts[0].severity > 0
    assert len(conflicts[0].evidence_ids) == 2


def test_no_conflict_when_only_one_side():
    engine = ConflictEngine(Settings())
    conflicts = engine.detect({"CLM_X": [_evidence("E_SUP", "SUPPORTS")]}, threshold=0.3)
    assert conflicts == []


def test_apply_to_belief_raises_uncertainty():
    engine = ConflictEngine(Settings())
    conflicts = engine.detect(
        {"CLM_X": [_evidence("E_SUP", "SUPPORTS"), _evidence("E_CON", "CONTRADICTS")]},
        threshold=0.3,
    )
    belief = Belief(id="b1", claim_id="CLM_X", statement="x", uncertainty=0.4)
    raised = engine.apply_to_belief(belief, conflicts[0])
    assert raised.uncertainty > belief.uncertainty
    assert raised.uncertainty <= 1.0
    assert raised.confidence < belief.confidence


def test_severity_bounded():
    engine = ConflictEngine(Settings())
    conflicts = engine.detect(
        {"CLM_X": [_evidence("E_SUP", "SUPPORTS"), _evidence("E_CON", "CONTRADICTS")]},
        threshold=0.0,
    )
    assert all(0 <= c.severity <= 1 for c in conflicts)
