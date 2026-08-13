"""v1.2 V-1 provenance + calibration acceptance tests."""

from __future__ import annotations

import pytest

from tests.conftest import make_belief
from vencertia.capabilities import DecisionCompiler
from vencertia.config import Settings
from vencertia.domain import (
    ApprovalStatus,
    CalibrationStatus,
    Decision,
    DecisionOption,
    EstimateType,
    ModelParameter,
    ProvenanceType,
    classify_calibration,
)
from vencertia.providers.mock import MockProvider
from vencertia.runtime.uncertainty_engine import compute_option_scores


def test_model_parameter_defaults():
    parameter = ModelParameter(value=0.8)
    assert parameter.provenance == "DOMAIN_DEFAULT"
    assert parameter.status == "APPROVED"
    with pytest.raises(ValueError):
        ModelParameter(value=0.8, unknown_field="nope")


def test_legacy_belief_coefficients_roundtrip():
    option = DecisionOption.model_validate(
        {"id": "a", "label": "a", "belief_coefficients": {"wtp": 0.8}}
    )
    assert option.effective_belief_coefficients["wtp"] == 0.8
    assert option.belief_parameters is None


def test_calibration_status_legacy_alias_and_classify():
    assert CalibrationStatus("CALIBRATED") == CalibrationStatus.CALIBRATED
    assert CalibrationStatus("UNCALIBRATED") == CalibrationStatus.UNCALIBRATED
    assert classify_calibration(0) == CalibrationStatus.UNCALIBRATED
    assert classify_calibration(10, min_samples=20) == CalibrationStatus.LOW_SAMPLE
    assert classify_calibration(25) == CalibrationStatus.DOMAIN_CALIBRATED


def test_estimate_type_default_is_unspecified():
    belief = make_belief("wtp", 0.7, 7, 3)
    assert belief.estimate_type == "UNSPECIFIED"
    assert belief.calibration_status == "UNCALIBRATED"
    assert EstimateType.UNSPECIFIED == "UNSPECIFIED"


def _base_decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[
            DecisionOption(id="a", label="a", belief_coefficients={"wtp": 0.5}),
            DecisionOption(id="b", label="b", belief_coefficients={"wtp": -0.3}),
        ],
        relevant_belief_ids=["wtp"],
    )


def test_compute_option_scores_parameters_equivalent():
    beliefs = [make_belief("wtp", 0.8, 8, 2)]
    base = _base_decision()
    with_params = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[
            DecisionOption(
                id="a", label="a", belief_coefficients={"wtp": 0.5},
                belief_parameters={"wtp": ModelParameter(value=0.5)},
            ),
            DecisionOption(
                id="b", label="b", belief_coefficients={"wtp": -0.3},
                belief_parameters={"wtp": ModelParameter(value=-0.3)},
            ),
        ],
        relevant_belief_ids=["wtp"],
    )
    base_scores = compute_option_scores(base, beliefs)
    param_scores = compute_option_scores(with_params, beliefs)
    assert [s.adjusted_utility for s in base_scores] == [
        s.adjusted_utility for s in param_scores
    ]


class _FakeLLM:
    """A model whose name is not mock → DecisionCompiler marks params PROPOSED."""

    name = "openai_compatible"

    def __init__(self) -> None:
        self._mock = MockProvider()

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        return self._mock.generate_structured(task, schema, context)

    def complete(self, prompt: str) -> str:
        return self._mock.complete(prompt)


def test_mock_compiler_leaves_belief_parameters_none():
    compiled = DecisionCompiler(model=MockProvider(), settings=Settings()).compile(
        "Should we commit six weeks to the MVP?",
        {"project_id": "PRJ_1", "user_id": "u1"},
    )
    for option in compiled.decision.options:
        assert option.belief_parameters is None


def test_llm_compiler_marks_parameters_proposed():
    compiled = DecisionCompiler(model=_FakeLLM(), settings=Settings()).compile(
        "Should we commit six weeks to the MVP?",
        {"project_id": "PRJ_1", "user_id": "u1"},
    )
    marked = [
        option
        for option in compiled.decision.options
        if option.belief_coefficients
    ]
    assert marked
    for option in marked:
        assert option.belief_parameters is not None
        for parameter in option.belief_parameters.values():
            assert parameter.provenance == "LLM_PROPOSED"
            assert parameter.status == "PROPOSED"
            assert ProvenanceType(parameter.provenance) == ProvenanceType.LLM_PROPOSED
            assert ApprovalStatus(parameter.status) == ApprovalStatus.PROPOSED
