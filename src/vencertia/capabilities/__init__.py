"""Capabilities package — replaceable inference modules (no write authority).

Also hosts the :class:`DecisionCompiler` which turns a problem statement into
candidate Objective/Decision/Claim/Belief structures via a ModelProvider.
"""

from __future__ import annotations

from vencertia.capabilities.base import Capability, CapabilityResult
from vencertia.capabilities.challenger import ChallengerCapability
from vencertia.capabilities.company_intelligence import CompanyIntelligenceCapability
from vencertia.capabilities.financial import FinancialCapability
from vencertia.capabilities.founder_diagnosis import FounderDiagnosisCapability
from vencertia.capabilities.gtm import GtmCapability
from vencertia.capabilities.market import MarketCapability
from vencertia.capabilities.research import ResearchCapability
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    ApprovalStatus,
    Belief,
    Claim,
    Decision,
    DecisionOption,
    Experiment,
    ModelParameter,
    Objective,
    ProvenanceType,
    VencertiaBaseModel,
)
from vencertia.providers.models import ModelProvider
from vencertia.repositories.base import Repository


class CompiledDecision(VencertiaBaseModel):
    """Candidate compile output: objective + decision + claims + beliefs."""

    objective: Objective
    decision: Decision
    claims: list[Claim] = []
    beliefs: list[Belief] = []
    experiments: list[Experiment] = []
    notes: list[str] = []


class DecisionCompiler:
    """Compiles a problem statement into candidate decision structures."""

    def __init__(
        self,
        model: ModelProvider,
        settings: Settings | None = None,
        repo: Repository | None = None,
    ) -> None:
        self.model = model
        self.settings = settings or get_settings()
        self.repo = repo

    def compile(
        self,
        problem: str,
        project_state: dict,
        options: list[DecisionOption] | None = None,
        context=None,
    ) -> CompiledDecision:
        context_payload = {}
        if context is not None:
            context_payload = {
                "claims": [
                    c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in getattr(context, "claims", []) or []
                ],
                "beliefs": [
                    b.model_dump(mode="json") if hasattr(b, "model_dump") else b
                    for b in getattr(context, "critical_assumptions", []) or []
                ],
                "evidence_count": len(getattr(context, "top_evidence", []) or []),
            }
        raw = self.model.generate_structured(
            task=f"Compile a decision structure for: {problem}",
            schema={"kind": "compile_decision"},
            context={
                "problem_text": problem,
                **project_state,
                "options": [o.model_dump(mode="json") for o in options] if options else None,
                "context": context_payload,
            },
        )
        objective_data = raw.get("objective") or {}
        decision_data = raw.get("decision") or {}
        # Link decision to objective after ids are known.
        objective = Objective.model_validate(objective_data)
        decision_data["objective_id"] = objective.id
        decision = Decision.model_validate(decision_data)
        # V-1: non-mock (LLM) models propose parameters, not approve them.
        if self._model_is_llm():
            decision = self._mark_parameters_proposed(decision)
        claims = [Claim.model_validate(c) for c in raw.get("claims") or []]
        beliefs = [Belief.model_validate(b) for b in raw.get("beliefs") or []]
        experiments = [Experiment.model_validate(e) for e in raw.get("experiments") or []]
        return CompiledDecision(
            objective=objective,
            decision=decision,
            claims=claims,
            beliefs=beliefs,
            experiments=experiments,
            notes=list(raw.get("notes") or []),
        )

    def _model_is_llm(self) -> bool:
        """A model with a non-mock ``name`` is treated as an LLM proposer."""
        return getattr(self.model, "name", None) not in (None, "mock")

    def _mark_parameters_proposed(self, decision: Decision) -> Decision:
        """Wrap LLM-produced float coefficients as PROPOSED ModelParameters (V-1).

        ``LLM_PROPOSED/PROPOSED`` records the provenance/approval semantics
        ("LLM propose ≠ approve") without blocking the deterministic engines.
        """
        for option in decision.options:
            if not option.belief_coefficients:
                continue
            parameters = dict(option.belief_parameters or {})
            for belief_id, value in option.belief_coefficients.items():
                parameters[belief_id] = ModelParameter(
                    value=value,
                    provenance=ProvenanceType.LLM_PROPOSED,
                    status=ApprovalStatus.PROPOSED,
                )
            option.belief_parameters = parameters
        return decision


def build_capability_registry(
    settings: Settings | None = None,
    repo: Repository | None = None,
    model: ModelProvider | None = None,
    search=None,
) -> dict[str, Capability]:
    """Instantiate all capability modules (defaults to mock providers)."""
    capabilities: dict[str, Capability] = {
        "founder_diagnosis": FounderDiagnosisCapability(),
        "market": MarketCapability(),
        "financial": FinancialCapability(),
        "challenger": ChallengerCapability(),
        "research": ResearchCapability(search=search),
        "gtm": GtmCapability(),
    }
    if repo is not None:
        capabilities["company_intelligence"] = CompanyIntelligenceCapability(repo)
    return capabilities


__all__ = [
    "Capability",
    "CapabilityResult",
    "ChallengerCapability",
    "CompanyIntelligenceCapability",
    "CompiledDecision",
    "DecisionCompiler",
    "FinancialCapability",
    "FounderDiagnosisCapability",
    "GtmCapability",
    "MarketCapability",
    "ResearchCapability",
    "build_capability_registry",
]
