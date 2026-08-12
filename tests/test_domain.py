"""Domain schema validation tests (extra=forbid, enums, defaults, IDs)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vencertia.domain import (
    Belief,
    Claim,
    Decision,
    DecisionOption,
    Evidence,
    MemoryRecord,
    MemoryScope,
    MemoryType,
    Objective,
    PredictionEntry,
    Project,
    Scope,
    utcnow,
)


def test_extra_forbid_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Evidence(
            id="E_1",
            scope=Scope.PROJECT,
            evidence_type="REAL_PAYMENT",
            source="x",
            bogus_field=1,
        )


def test_enum_values_serialize_as_strings():
    e = Evidence(
        id="E_1", scope=Scope.PROJECT, evidence_type="REAL_PAYMENT", source="x"
    )
    assert e.scope == "PROJECT"
    assert e.evidence_type == "REAL_PAYMENT"
    assert e.authority_level == "MODEL_PRIOR"  # default


def test_belief_probability_syncs_with_posterior():
    b = Belief(id="BLF_1", claim_id="CLM_1", statement="x", posterior=0.75)
    assert b.probability == 0.75
    b.posterior = 0.2
    assert b.probability == 0.2


def test_id_prefixes_and_defaults():
    now = utcnow()
    obj = Objective(id="OBJ_1", owner="u1", name="n", description="d")
    assert obj.priority == 5
    assert obj.weight == 1.0
    assert obj.created_at <= utcnow()
    assert obj.created_at.tzinfo is not None  # UTC aware


def test_decision_requires_at_least_one_option():
    with pytest.raises(ValidationError):
        Decision(
            id="DEC_1",
            decision_question="q",
            objective_id="OBJ_1",
            project_id="PRJ_1",
            options=[],
        )


def test_prediction_probability_bounds():
    with pytest.raises(ValidationError):
        PredictionEntry(
            id="PRD_1",
            project_id="PRJ_1",
            target="x",
            predicted_probability=0.0,  # must be >0
        )
    with pytest.raises(ValidationError):
        PredictionEntry(
            id="PRD_1",
            project_id="PRJ_1",
            target="x",
            predicted_probability=1.0,  # must be <1
        )


def test_claim_scope_required():
    with pytest.raises(ValidationError):
        Claim(id="CLM_1", statement="x")


def test_memory_record_v10_2_contract():
    m = MemoryRecord(
        memory_id="M_1",
        user_id="u1",
        scope=MemoryScope.USER_GLOBAL,
        memory_type=MemoryType.CONSTRAINT,
        content="10h/week",
        fact_status="VERIFIED",
    )
    assert m.scope == "USER_GLOBAL"
    assert m.memory_type == "CONSTRAINT"
    assert m.id == "M_1"


def test_decision_option_kind_accepts_enum_values():
    o = DecisionOption(id="o1", label="Go", kind="CONDITIONAL_GO", base_utility=0.5)
    assert o.kind == "CONDITIONAL_GO"


def test_project_defaults():
    p = Project(id="PRJ_1", user_id="u1", name="n")
    assert p.status == "IDEA"
    assert p.stage == "S0_INITIALIZATION"
    assert p.is_primary is False
