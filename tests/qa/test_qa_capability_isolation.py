"""QA adversarial tests — Requirement 1: Agent/LLM 无 canonical state mutation authority.

The capability layer must be candidate-producer only. These tests prove that
an LLM output (compiled beliefs / evidence / decision skeleton) can never
directly mutate persisted canonical state; only the deterministic engine
pipeline may do so.
"""

from __future__ import annotations

import pytest

from vencertia.capabilities.base import Capability, CapabilityResult
from vencertia.domain import Belief, Direction, Evidence, Project, Scope, Verification
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockSearchProvider, MockRetrievalProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest


class EvilBeliefProvider:
    """A malicious model that tries to write a 0.99 posterior for an EXISTING claim."""

    name = "evil_belief"

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        raw = MockProvider().generate_structured(task, schema, context)
        for belief in raw.get("beliefs", []):
            if belief.get("id") == "wtp":
                belief["posterior"] = 0.99
                belief["probability"] = 0.99
                belief["alpha"] = 99.0
                belief["beta"] = 1.0
        return raw


def _seed_canonical_wtp(repo: InMemoryRepository, project_id: str = "PRJ_EVIL") -> None:
    repo.save_project(Project(id=project_id, user_id="u1", name="p"))
    repo.save_belief(
        Belief(
            id="wtp",
            claim_id="CLM_WTP",
            statement="ICP will pay",
            scope=Scope.PROJECT,
            project_id=project_id,
            prior=0.5,
            posterior=0.5,
            probability=0.5,
            alpha=1.0,
            beta=1.0,
            decision_relevant=True,
        )
    )


def test_llm_compiled_belief_cannot_overwrite_existing_canonical_state() -> None:
    """LLM returns wtp=0.99 for an existing claim; canonical repo belief must stay 0.5."""
    repo = InMemoryRepository()
    _seed_canonical_wtp(repo)
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(repo=repo, bus=bus, model=EvilBeliefProvider())
    orchestrator.solve(
        SolveRequest(
            project_id="PRJ_EVIL",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    stored = repo.get_belief("wtp")
    assert stored is not None
    # The LLM's 0.99 must never become canonical state.
    assert abs(stored.probability - 0.99) > 1e-9
    # The canonical belief is still the deterministic prior (no pseudo-count added
    # by LLM compile; existing canonical state wins per _persist_compiled).
    assert stored.alpha == 1.0
    assert stored.beta == 1.0


def test_capability_protocol_exposes_no_write_api() -> None:
    """The Capability protocol must not expose repository write methods."""
    members = set(Capability.__dict__.keys()) | {"name", "run"}
    # No persistence / mutation entry points.
    assert not members.intersection(
        {"save_belief", "save_decision", "add_evidence", "save_project", "save_experiment"}
    )
    # CapabilityResult carries only candidate data.
    fields = set(CapabilityResult.model_fields.keys())
    assert fields <= {"claims", "evidence", "decision_skeleton", "experiments", "notes"}


def test_llm_evidence_cannot_self_declare_verified_through_pipeline() -> None:
    """LLM evidence claiming VERIFIED must be downgraded to ESTIMATED at the gate."""
    repo = InMemoryRepository()
    repo.save_project(Project(id="PRJ_EV", user_id="u1", name="p"))
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(repo=repo, bus=bus, model=MockProvider())
    evidence = Evidence(
        id="E_LLM_EVIL",
        claim_ids=["CLM_WTP"],
        scope=Scope.PROJECT,
        evidence_type="LLM_INFERENCE",
        source="model says verified",
        supports_or_contradicts=Direction.SUPPORTS.value,
        verification=Verification.VERIFIED,
    )
    # Ingest via the orchestrator's gated path (not a direct repo write).
    applied = orchestrator._ingest_evidence([evidence])
    assert len(applied) == 1
    stored = repo.get_evidence("E_LLM_EVIL")
    assert stored.verification == Verification.ESTIMATED.value  # downgraded
    assert stored.authority_level == "LLM_INFERENCE"


def test_decision_compiler_never_persists_by_itself() -> None:
    """DecisionCompiler.compile must be side-effect free (no repo writes)."""
    repo = InMemoryRepository()
    from vencertia.capabilities import DecisionCompiler

    compiler = DecisionCompiler(model=MockProvider(), repo=repo)

    def _explode(*args, **kwargs):
        raise AssertionError("capability must not write to the repository")

    repo.save_belief = _explode  # type: ignore[assignment]
    repo.save_decision = _explode  # type: ignore[assignment]
    repo.add_evidence = _explode  # type: ignore[assignment]
    compiled = compiler.compile(
        "Should we commit six weeks to the MVP?",
        {"project_id": "PRJ_C", "user_id": "u1", "domain": "general", "model_tag": "mock"},
    )
    # Compile output is a candidate; belief values are still LLM-claimed.
    assert compiled.decision.id.startswith("DEC_")
    assert compiled.beliefs
