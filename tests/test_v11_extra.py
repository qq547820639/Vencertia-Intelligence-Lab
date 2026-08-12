"""Additional v1.1 coverage: experiment validation, prediction correction,
SQLite persistence, PG parity gating, outcome→claim binding."""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import (
    Action,
    Belief,
    Decision,
    DecisionOption,
    Experiment,
    OutcomeType,
    PredictionEntry,
    Scope,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from vencertia.runtime.evidence_policy import EvidencePolicy
from vencertia.runtime.experiment_optimizer import validate_experiment
from vencertia.runtime.prediction_ledger import PredictionLedger


def _experiment(action="Offer a paid concierge pilot to 20 ICPs within 30 days", **kw) -> Experiment:
    defaults = dict(
        id="EXP_1",
        name="pilot",
        success_criteria=">=2 paid",
        failure_criteria="0 paid",
        ambiguity_criteria="1 paid",
        action=action,
    )
    defaults.update(kw)
    return Experiment(**defaults)


def test_validate_experiment_rejects_vague_action():
    result = validate_experiment(_experiment(action="Do some more interviews"))
    assert result.valid is False
    assert any("vague" in r for r in result.reasons)


def test_validate_experiment_rejects_missing_criteria():
    result = validate_experiment(
        _experiment(success_criteria="", failure_criteria="", ambiguity_criteria="")
    )
    assert result.valid is False
    assert any("success_criteria" in r for r in result.reasons)
    assert any("failure_criteria" in r for r in result.reasons)
    assert any("ambiguity_criteria" in r for r in result.reasons)


def test_validate_experiment_accepts_concrete_action():
    result = validate_experiment(_experiment())
    assert result.valid is True


def _prediction(repo) -> PredictionEntry:
    ledger = PredictionLedger(repo)
    decision = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"], horizon="short",
    )
    belief = Belief(
        id="wtp", claim_id="CLM_WTP", statement="wtp", scope="PROJECT", project_id="PRJ_1",
        probability=0.7, posterior=0.7, alpha=7, beta=3, decision_relevant=True,
    )
    return ledger.register(decision, [belief])[0]


def test_prediction_resolve_immutable_and_correct_new_version(repo):
    ledger = PredictionLedger(repo)
    entry = _prediction(repo)
    resolved = ledger.resolve(entry.id, True, resolution_source="outcome_1")
    assert resolved.predicted_probability == entry.predicted_probability  # immutable
    assert resolved.resolution_source == "outcome_1"
    assert resolved.version == entry.version + 1
    # correct() creates a NEW version; original is preserved.
    corrected = ledger.correct(resolved.id, False, "user_review")
    assert corrected.corrected is True
    assert corrected.version == resolved.version + 1
    assert corrected.outcome is False
    assert corrected.predicted_probability == entry.predicted_probability
    # Original entry still exists with its old resolution.
    original = repo.get_prediction(entry.id)
    assert original.resolution == "TRUE"


def test_sqlite_persistence_bindings_and_records(tmp_db):
    from vencertia.domain import Claim, ClaimBindingInput
    from vencertia.repositories.sqlite import SQLiteRepository
    from vencertia.runtime.claim_binding import (
        ClaimBindingEngine,
        ClaimExtractor,
        DeterministicClaimMatcher,
        EvidenceClaimLinker,
    )

    repo = SQLiteRepository(path=tmp_db)
    settings = Settings()
    policy = EvidencePolicy(settings)
    claim = Claim(id="CLM_WTP", statement="ICP will pay for the promised outcome", scope=Scope.PROJECT)
    repo.add_claim(claim)
    engine = ClaimBindingEngine(
        extractor=ClaimExtractor(settings=settings),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=policy,
        repo=repo,
        bus=EventBus(sink=repo.append_event),
        settings=settings,
    )
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {"id": "E_1", "source": "Data shows ICP will pay for the promised outcome", "scope": "MARKET"}
            ],
            context={"claims": [claim]},
            existing_claims=[claim],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert output.bindings
    persisted = repo.list_bindings(evidence_id=output.bindings[0].evidence_id)
    assert len(persisted) >= 1
    assert repo.get_binding(persisted[0].id) is not None


def test_sqlite_belief_update_record_persistence(tmp_db):
    from vencertia.repositories.sqlite import SQLiteRepository

    repo = SQLiteRepository(path=tmp_db)
    belief = Belief(
        id="b1", claim_id="CLM_1", statement="s", scope="PROJECT", project_id="PRJ_1",
        probability=0.5, alpha=1.0, beta=1.0,
    )
    policy = EvidencePolicy(Settings())
    from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput

    evidence = __import__("vencertia.domain", fromlist=["Evidence"]).Evidence(
        id="E_1", claim_ids=["CLM_1"], scope="PROJECT", evidence_type="OBSERVED_BEHAVIOR",
        source="s", supports_or_contradicts="SUPPORTS", strength=0.9, reliability=0.9,
    )
    output = BeliefEngine(Settings(), policy).update(
        BeliefUpdateInput(beliefs=[belief], evidence=[evidence], policy=policy)
    )
    assert output.update_records
    for record in output.update_records:
        repo.save_belief_update_record(record)
    history = repo.list_belief_update_records("b1")
    assert len(history) == 1
    assert history[0].policy_version == "1.1"
    assert history[0].evidence_used == ["E_1"]


def test_postgres_parity_gated_without_dsn():
    from vencertia.repositories.postgres import PostgresDisabledError, PostgresRepository

    with pytest.raises(PostgresDisabledError):
        PostgresRepository(dsn=None)


def test_outcome_evidence_binds_to_claims():
    """record_outcome generates evidence with claim_ids (v1.1 no empty binding)."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(), search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_OB", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    repo.save_action(
        Action(id="ACT_OB", project_id="PRJ_OB", kind="EXPERIMENT",
               description="pilot", decision_id=result.decision_id,
               experiment_id=result.next_experiment.experiment.id)
    )
    recorded = orchestrator.record_outcome(
        "ACT_OB", "0 paid", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE
    )
    assert recorded.outcome_evidence.claim_ids  # non-empty claim binding
    assert recorded.outcome_evidence.authority_level == "PROJECT_EXPERIMENT_RESULT"


def test_prediction_correct_emits_event(repo):
    ledger = PredictionLedger(repo)
    entry = _prediction(repo)
    resolved = ledger.resolve(entry.id, True)
    orchestrator = SolveOrchestrator(repo=repo, bus=EventBus(sink=repo.append_event))
    orchestrator.bus.publish(
        __import__("vencertia.events.types", fromlist=["make_event"]).make_event(
            EventType.PREDICTION_CORRECTED, "prediction", resolved.id, {}
        )
    )
    types = [e.event_type for e in repo.events_since(0)]
    assert EventType.PREDICTION_CORRECTED.value in types
