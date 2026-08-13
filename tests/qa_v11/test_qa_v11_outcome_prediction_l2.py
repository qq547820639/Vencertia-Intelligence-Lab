"""QA adversarial tests — Outcome→claim binding + Prediction immutability + L2 (P0).

Verifies: experiment outcome evidence binds the corresponding claim and moves
the belief; predictions are immutable after resolve; correct() creates a new
version without overwriting; L2 register→settle is a closed loop that does not
leak into L0/L1 data.
"""

from __future__ import annotations

import pytest

from vencertia.domain import (
    Action,
    Decision,
    DecisionOption,
    OutcomeType,
    PredictionEntry,
    Scope,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from vencertia.runtime.prediction_ledger import PredictionLedger


def _orchestrator() -> tuple[SolveOrchestrator, InMemoryRepository]:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(), search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    return orchestrator, repo


def test_qa_outcome_evidence_binds_claim_and_moves_belief():
    """Experiment outcome evidence must bind the claim (claim_ids non-empty) and update belief."""
    orchestrator, repo = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_QA_OB", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    action = Action(
        id="ACT_QA_OB", project_id="PRJ_QA_OB", kind="EXPERIMENT",
        description="paid pilot", decision_id=result.decision_id,
        experiment_id=result.next_experiment.experiment.id,
        status="RUNNING",
    )
    repo.save_action(action)
    beliefs_before = {b.id: b.probability for b in repo.get_beliefs("PRJ_QA_OB")}

    recorded = orchestrator.record_outcome(
        "ACT_QA_OB", "0 paid in pilot", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE
    )
    # v1.1 invariant: outcome evidence is bound to claims, NOT claim_ids=[].
    assert recorded.outcome_evidence.claim_ids, "outcome evidence must bind claims"
    assert recorded.outcome_evidence.authority_level == "PROJECT_EXPERIMENT_RESULT"

    # The belief referenced by quantitative {"wtp": 0.0} must have moved down.
    beliefs_after = {b.id: b.probability for b in repo.get_beliefs("PRJ_QA_OB")}
    assert beliefs_after["wtp"] < beliefs_before["wtp"]
    # And a belief-update record was persisted for the outcome round.
    records = repo.list_belief_update_records("wtp")
    assert records, "outcome round must persist a BeliefUpdateRecord"


def _registered(repo) -> tuple[PredictionLedger, PredictionEntry]:
    ledger = PredictionLedger(repo)
    decision = Decision(
        id="DEC_QA_P", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"], horizon="short",
    )
    from vencertia.domain import Belief

    belief = Belief(
        id="wtp", claim_id="CLM_WTP", statement="wtp", scope=Scope.PROJECT, project_id="PRJ_1",
        probability=0.7, posterior=0.7, alpha=7, beta=3, decision_relevant=True,
    )
    entry = ledger.register(decision, [belief])[0]
    repo.save_prediction(entry)  # M0-4: register() no longer persists
    return ledger, entry


def test_qa_prediction_resolve_is_immutable():
    """resolve() adds resolution but never rewrites predicted_probability."""
    repo = InMemoryRepository()
    ledger, entry = _registered(repo)
    resolved = ledger.resolve(entry.id, True, resolution_source="outcome_xyz")
    assert resolved.predicted_probability == entry.predicted_probability
    assert resolved.belief_snapshot == entry.belief_snapshot
    assert resolved.resolution == "TRUE"
    assert resolved.resolution_source == "outcome_xyz"
    assert resolved.version == entry.version + 1

    # Double resolve is rejected.
    with pytest.raises(ValueError):
        ledger.resolve(resolved.id, False)


def test_qa_prediction_correct_creates_new_version():
    """correct() -> new id, corrected=True, original preserved."""
    repo = InMemoryRepository()
    ledger, entry = _registered(repo)
    resolved = ledger.resolve(entry.id, True, resolution_source="o1")
    corrected = ledger.correct(resolved.id, False, "user_review")
    assert corrected.id != resolved.id
    assert corrected.corrected is True
    assert corrected.outcome is False
    assert corrected.predicted_probability == entry.predicted_probability  # snapshot immutable
    # Original untouched.
    original = repo.get_prediction(entry.id)
    assert original.resolution == "TRUE"
    assert original.outcome is True
    # New version is retrievable.
    assert repo.get_prediction(corrected.id) is not None


def test_qa_correct_requires_settled():
    repo = InMemoryRepository()
    ledger, entry = _registered(repo)
    with pytest.raises(ValueError):
        ledger.correct(entry.id, False, "user")  # open entry


def test_qa_l2_register_settle_closed_loop():
    """L2: register -> due -> settle is a closed loop with immutable probability."""
    from vencertia.benchmark.l2 import L2Runner

    repo = InMemoryRepository()
    runner = L2Runner(repo=repo)
    entry = PredictionEntry(
        id="PRD_L2_QA", project_id="PRJ_L2", claim_id="CLM_X", target="t",
        predicted_probability=0.6, due_at=utcnow(),
    )
    runner.register(entry)
    assert repo.get_prediction("PRD_L2_QA") is not None
    settled = runner.settle("PRD_L2_QA", True, "user_alice")
    assert settled.resolution == "TRUE"
    assert settled.predicted_probability == 0.6  # immutable
    assert settled.resolution_source == "user_alice"


def test_qa_l2_does_not_leak_into_l0_l1():
    """L2 prospective data must not appear in L0/L1 benchmark sources."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]  # repo root: tests/qa_v11 -> tests -> root
    l0 = root / "data/benchmarks/l0_cases.json"
    l1 = root / "data/benchmarks/l1_cases.jsonl"
    l2_dir = root / "data/benchmarks/l2"

    import json

    l0_cases = json.loads(l0.read_text(encoding="utf-8"))
    ids = {c.get("id") for c in l0_cases} if isinstance(l0_cases, list) else set()
    if isinstance(l0_cases, dict):
        for v in l0_cases.values():
            if isinstance(v, list):
                ids |= {c.get("id") for c in v}
    assert not any(str(i).startswith("PRD_") for i in ids)

    if l1.exists():
        for line in l1.read_text(encoding="utf-8").splitlines():
            if line.strip():
                payload = json.loads(line)
                assert not str(payload.get("id", "")).startswith("PRD_")
    # L2 registry lives in its own directory.
    assert (l2_dir / "README.md").exists()
