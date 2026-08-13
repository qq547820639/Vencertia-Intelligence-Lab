"""v1.2 V-4 stakes / adaptive ABSTAIN acceptance tests."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Decision, DecisionOption, StakesClass, StakesProfile
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput


def _decision(stakes_class: str, stakes: StakesProfile | None = None) -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[
            DecisionOption(id="a", label="a", base_utility=0.1),
            DecisionOption(id="b", label="b", base_utility=0.0),
        ],
        stakes_class=stakes_class,
        stakes=stakes,
    )


def test_stakes_threshold_bands_defaults():
    settings = Settings()
    assert settings.stakes_thresholds["MEDIUM"] == {
        "minimum_margin": 0.08, "max_critical_uncertainty": 0.45,
    }
    assert settings.stakes_thresholds["HIGH"] == {
        "minimum_margin": 0.12, "max_critical_uncertainty": 0.35,
    }
    assert settings.stakes_thresholds["LOW"] == {
        "minimum_margin": 0.04, "max_critical_uncertainty": 0.60,
    }


def test_margin_0_10_goes_under_medium_but_abstains_under_high():
    engine = DecisionEngine()
    medium = engine.evaluate(
        DecisionEngineInput(decision=_decision("MEDIUM"), beliefs=[])
    )
    assert medium.status == "GO"

    high = engine.evaluate(
        DecisionEngineInput(
            decision=_decision("HIGH", stakes=StakesProfile()), beliefs=[]
        )
    )
    assert high.status == "ABSTAIN"
    assert high.stakes_class == "HIGH"
    assert high.abstain_exit_condition


def test_default_stakes_class_is_medium():
    decision = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
    )
    assert decision.stakes_class == "MEDIUM"
    assert StakesClass.MEDIUM == "MEDIUM"
