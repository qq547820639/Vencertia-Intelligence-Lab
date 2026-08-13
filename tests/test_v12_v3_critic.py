"""v1.2 V-3 model critic acceptance tests."""

from __future__ import annotations

from vencertia.capabilities.base import CapabilityResult
from vencertia.capabilities.challenger import ChallengerCapability
from vencertia.domain import Belief, ModelCriticGate
from vencertia.domain.context import ContextBundle


def _context() -> ContextBundle:
    return ContextBundle(
        user_id="u1",
        critical_assumptions=[
            Belief(
                id="wtp", claim_id="CLM_WTP", statement="wtp",
                scope="PROJECT", project_id="PRJ_1",
            )
        ],
    )


def test_challenger_emits_structured_critique():
    result = ChallengerCapability().run("critique this decision", _context())
    assert result.critique is not None
    assert result.critique.model_risk in ("LOW", "MEDIUM", "HIGH")
    assert "MISSING_VARIABLE" in result.critique.findings
    assert "DOUBLE_COUNTING" in result.critique.findings
    assert result.critique.recommendation


def test_legacy_capability_result_has_no_critique():
    result = CapabilityResult(evidence=[])
    assert result.critique is None


def test_model_critic_gate_ordering():
    assert ModelCriticGate.should_require(None) is False
    assert ModelCriticGate.should_require("HIGH", "HIGH") is True
    assert ModelCriticGate.should_require("MEDIUM", "HIGH") is False
    assert ModelCriticGate.should_require("LOW", "MEDIUM") is False
    assert ModelCriticGate.should_require("MEDIUM", "MEDIUM") is True
