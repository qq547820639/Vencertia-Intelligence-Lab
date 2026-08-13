"""Repository contracts and errors.

The repository layer is the ONLY state-mutation entry point (ADR-002).
Every write uses optimistic locking: callers load an object, mutate it, then
save with the expected version. A stale write raises :class:`StaleWriteError`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from vencertia.domain import (
    Action,
    Belief,
    BeliefUpdateRecord,
    CandidateClaim,
    Claim,
    CompanyCase,
    Decision,
    DecisionOutcomeRecord,
    DecisionRecord,
    DecisionSensitivity,
    DecisionTrace,
    Evidence,
    EvidenceClaimBinding,
    EvidenceConflict,
    Experiment,
    FinancialSnapshot,
    FounderOpportunityPortfolio,
    FounderProfile,
    MemoryRecord,
    Objective,
    Outcome,
    PredictionEntry,
    Project,
    ProviderCallRecord,
    ResearchPlan,
    ResearchTrace,
    Rule,
    RuleKind,
    Scope,
    VencertiaBaseModel,
    utcnow,
)
from vencertia.events.types import DomainEvent

T = TypeVar("T", bound=VencertiaBaseModel)


class StaleWriteError(Exception):
    """Raised when an optimistic-lock write targets a stale version."""

    def __init__(self, entity_type: str, entity_id: str, expected_version: int) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected_version = expected_version
        super().__init__(
            f"Stale write for {entity_type}:{entity_id} (expected version {expected_version})"
        )


class EntityNotFoundError(Exception):
    """Raised when an entity does not exist (maps to HTTP 404)."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")


class PostgresDisabledError(Exception):
    """Raised when the PostgreSQL backend is used without a DSN / driver."""


@runtime_checkable
class Repository(Protocol):
    """Persistence interface used by the runtime and engines."""

    # Evidence / Claim
    def add_evidence(self, evidence: Evidence, *, allow_missing_project: bool = False) -> None: ...
    def get_evidence(self, evidence_id: str) -> Evidence | None: ...
    def list_evidence(
        self,
        claim_ids: list[str] | None = None,
        project_id: str | None = None,
        include_shared: bool = True,
    ) -> list[Evidence]: ...
    def add_claim(self, claim: Claim) -> None: ...
    def get_claim(self, claim_id: str) -> Claim | None: ...
    def list_claims(self, project_id: str | None = None) -> list[Claim]: ...

    # Belief
    def get_beliefs(self, project_id: str, as_of: datetime | None = None) -> list[Belief]: ...
    def get_belief(self, belief_id: str) -> Belief | None: ...
    def save_belief(self, belief: Belief, expected_version: int | None = None) -> None: ...

    # Decision
    def save_decision(self, decision: Decision, expected_version: int | None = None) -> None: ...
    def get_decision(self, decision_id: str) -> Decision | None: ...
    def list_decisions(self, project_id: str | None = None) -> list[Decision]: ...

    # Experiment
    def save_experiment(self, experiment: Experiment, expected_version: int | None = None) -> None: ...
    def get_experiment(self, experiment_id: str) -> Experiment | None: ...
    def list_experiments(self, project_id: str | None = None) -> list[Experiment]: ...

    # Action / Outcome
    def save_action(self, action: Action, expected_version: int | None = None) -> None: ...
    def get_action(self, action_id: str) -> Action | None: ...
    def list_actions(
        self,
        project_id: str | None = None,
        decision_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[Action]: ...
    def save_outcome(self, outcome: Outcome, expected_version: int | None = None) -> None: ...
    def get_outcome(self, outcome_id: str) -> Outcome | None: ...
    def list_outcomes(
        self,
        project_id: str | None = None,
        action_id: str | None = None,
    ) -> list[Outcome]: ...

    # Prediction
    def save_prediction(self, entry: PredictionEntry, expected_version: int | None = None) -> None: ...
    def get_prediction(self, prediction_id: str) -> PredictionEntry | None: ...
    def get_open_predictions(self, project_id: str) -> list[PredictionEntry]: ...
    def list_predictions(self, project_id: str | None = None) -> list[PredictionEntry]: ...
    def resolve_prediction(self, prediction_id: str, outcome: bool) -> PredictionEntry: ...

    # Project / Objective / Founder / Financial / Company / Memory / Rules
    def save_project(self, project: Project, expected_version: int | None = None) -> None: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def list_projects(self, user_id: str | None = None) -> list[Project]: ...
    def save_objective(self, objective: Objective, expected_version: int | None = None) -> None: ...
    def get_objective(self, objective_id: str) -> Objective | None: ...
    def save_founder_profile(self, profile: FounderProfile, expected_version: int | None = None) -> None: ...
    def get_founder_profile(self, user_id: str) -> FounderProfile | None: ...
    def save_financial_snapshot(self, fs: FinancialSnapshot, expected_version: int | None = None) -> None: ...
    def list_financial_snapshots(self, project_id: str) -> list[FinancialSnapshot]: ...
    def save_company_case(self, case: CompanyCase, expected_version: int | None = None) -> None: ...
    def get_company_case(self, company_id: str) -> CompanyCase | None: ...
    def list_company_cases(self) -> list[CompanyCase]: ...
    def save_memory(self, memory: MemoryRecord, expected_version: int | None = None) -> None: ...
    def get_memory(self, memory_id: str) -> MemoryRecord | None: ...
    def save_portfolio(self, portfolio: FounderOpportunityPortfolio) -> None: ...
    def get_portfolio(self, user_id: str) -> FounderOpportunityPortfolio | None: ...
    def get_rules(self, kind: RuleKind | None = None) -> list[Rule]: ...
    def save_rule(self, rule: Rule) -> None: ...

    # Events
    def append_event(self, event: DomainEvent) -> None: ...
    def events_since(self, after_seq: int) -> list[DomainEvent]: ...
    def in_transaction(self, fn: Callable[[], None]) -> None: ...

    # -- v1.1 claim binding ---------------------------------------------------
    def save_binding(self, binding: EvidenceClaimBinding, expected_version: int | None = None) -> None: ...
    def get_binding(self, binding_id: str) -> EvidenceClaimBinding | None: ...
    def list_bindings(
        self,
        evidence_id: str | None = None,
        claim_id: str | None = None,
        status: str | None = None,
    ) -> list[EvidenceClaimBinding]: ...
    def save_candidate_claim(self, candidate: CandidateClaim, expected_version: int | None = None) -> None: ...
    def list_candidate_claims(self, validation_status: str | None = None) -> list[CandidateClaim]: ...

    # -- v1.1 belief update records ---------------------------------------------
    def save_belief_update_record(self, record: BeliefUpdateRecord) -> None: ...
    def list_belief_update_records(self, belief_id: str) -> list[BeliefUpdateRecord]: ...

    # -- v1.1 research -----------------------------------------------------------
    def save_research_plan(self, plan: ResearchPlan) -> None: ...
    def get_research_plan(self, plan_id: str) -> ResearchPlan | None: ...
    def list_research_plans(self, decision_id: str) -> list[ResearchPlan]: ...
    def save_research_trace(self, trace: ResearchTrace) -> None: ...
    def list_research_traces(self, decision_id: str) -> list[ResearchTrace]: ...

    # -- v1.1 decision trace / sensitivity ----------------------------------------
    def save_decision_trace(self, trace: DecisionTrace) -> None: ...
    def get_decision_trace(self, decision_id: str) -> DecisionTrace | None: ...
    def save_decision_sensitivity(
        self, sensitivity: DecisionSensitivity, expected_version: int | None = None
    ) -> None: ...
    def get_decision_sensitivity(self, decision_id: str) -> DecisionSensitivity | None: ...

    # -- v1.1 evidence conflict -----------------------------------------------------
    def save_evidence_conflict(
        self, conflict: EvidenceConflict, expected_version: int | None = None
    ) -> None: ...
    def list_evidence_conflicts(self, claim_id: str | None = None) -> list[EvidenceConflict]: ...

    # -- v1.1 observability ----------------------------------------------------------
    def save_call_record(self, record: ProviderCallRecord) -> None: ...
    def list_call_records(
        self, kind: str | None = None, since: datetime | None = None
    ) -> list[ProviderCallRecord]: ...

    # -- v1.2 decision ledger (V-2) ---------------------------------------------------
    def save_decision_record(
        self, record: DecisionRecord, expected_version: int | None = None
    ) -> None: ...
    def get_decision_record(self, decision_id: str) -> DecisionRecord | None: ...
    def list_decision_records(self, project_id: str | None = None) -> list[DecisionRecord]: ...
    def save_decision_outcome_record(self, record: DecisionOutcomeRecord) -> None: ...
    def list_decision_outcome_records(
        self, decision_record_id: str
    ) -> list[DecisionOutcomeRecord]: ...


# Entity type keys (stored in the generic entities table)
ENTITY_TYPES: dict[str, type[VencertiaBaseModel]] = {
    "evidence": Evidence,
    "claim": Claim,
    "belief": Belief,
    "decision": Decision,
    "experiment": Experiment,
    "action": Action,
    "outcome": Outcome,
    "prediction": PredictionEntry,
    "project": Project,
    "objective": Objective,
    "founder_profile": FounderProfile,
    "financial_snapshot": FinancialSnapshot,
    "company_case": CompanyCase,
    "memory": MemoryRecord,
    "rule": Rule,
    "portfolio": FounderOpportunityPortfolio,
    # v1.1 entity types (generic entities table)
    "binding": EvidenceClaimBinding,
    "candidate_claim": CandidateClaim,
    "research_plan": ResearchPlan,
    "research_trace": ResearchTrace,
    "decision_sensitivity": DecisionSensitivity,
    "decision_trace": DecisionTrace,
    "evidence_conflict": EvidenceConflict,
    "call_record": ProviderCallRecord,
    "belief_update_record": BeliefUpdateRecord,
    # v1.2 entity types (generic entities table, no new migration)
    "decision_record": DecisionRecord,
    "decision_outcome_record": DecisionOutcomeRecord,
}


class EntityStoreMixin:
    """Domain-level CRUD implemented once on top of backend primitives.

    Subclasses (SQLite/Postgres/InMemory) implement:
      _load / _store / _list_all / _delete / _append_event / _events_since / _txn
    """

    entity_types: ClassVar[dict[str, type[VencertiaBaseModel]]] = ENTITY_TYPES

    # -- primitives (overridden by backends) -------------------------------

    def _load(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:  # pragma: no cover
        raise NotImplementedError

    def _store(
        self,
        entity_type: str,
        obj: VencertiaBaseModel,
        expected_version: int | None = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    def _list_all(self, entity_type: str) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def _delete(self, entity_type: str, entity_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def _append_event(self, event: DomainEvent) -> int:  # pragma: no cover
        raise NotImplementedError

    def _events_since(self, after_seq: int) -> list[DomainEvent]:  # pragma: no cover
        raise NotImplementedError

    def _txn(self, fn: Callable[[], None]) -> None:  # pragma: no cover
        fn()

    # -- generic helpers ----------------------------------------------------

    def _kind_of(self, obj: VencertiaBaseModel) -> str:
        for kind, model in self.entity_types.items():
            if isinstance(obj, model):
                return kind
        raise TypeError(f"Unregistered entity type: {type(obj).__name__}")

    def _save(self, obj: VencertiaBaseModel, expected_version: int | None = None) -> None:
        self._store(self._kind_of(obj), obj, expected_version)

    def _get(self, entity_type: str, entity_id: str) -> Any | None:
        row = self._load(entity_type, entity_id)
        if row is None:
            return None
        return self.entity_types[entity_type].model_validate(row)

    def _list(self, entity_type: str) -> list[Any]:
        model = self.entity_types[entity_type]
        return [model.model_validate(row) for row in self._list_all(entity_type)]

    # -- domain methods ------------------------------------------------------

    def add_evidence(
        self, evidence: Evidence, *, allow_missing_project: bool = False
    ) -> None:
        """Persist evidence with the v1.1.2 tenant-isolation write boundary.

        PROJECT/CUSTOMER-scoped evidence MUST carry ``project_id`` unless
        ``allow_missing_project=True`` (migration/import path only, ADR-014).
        MARKET/WORLD/COMPANY_CASE evidence may be shared with ``project_id=None``.
        """
        scope = evidence.scope.value if hasattr(evidence.scope, "value") else str(evidence.scope)
        if (
            not allow_missing_project
            and scope in (Scope.PROJECT.value, Scope.CUSTOMER.value)
            and not evidence.project_id
        ):
            raise ValueError(
                f"project-scoped evidence requires project_id (scope={scope}, id={evidence.id}) "
                f"— v1.1.2 integrity rule"
            )
        self._save(evidence)

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self._get("evidence", evidence_id)

    def list_evidence(
        self,
        claim_ids: list[str] | None = None,
        project_id: str | None = None,
        include_shared: bool = True,
    ) -> list[Evidence]:
        """List evidence with the v1.1.2 tenant-isolation read boundary.

        When ``project_id`` is given, only evidence owned by that project plus
        shared external evidence (WORLD/MARKET/COMPANY_CASE with
        ``project_id=None``) is returned. COMPANY_CASE sharing remains subject
        to the ADR-004 transferability gate at the policy layer. When
        ``project_id`` is None the full store is returned (technical queries,
        e.g. fingerprint de-dup).
        """
        rows = self._list("evidence")
        if project_id is not None:
            out: list[Evidence] = []
            for e in rows:
                if e.project_id == project_id:
                    out.append(e)
                elif include_shared and e.project_id is None:
                    scope = e.scope.value if hasattr(e.scope, "value") else str(e.scope)
                    if scope in (
                        Scope.WORLD.value,
                        Scope.MARKET.value,
                        Scope.COMPANY_CASE.value,
                    ):
                        out.append(e)
            rows = out
        if claim_ids is not None:
            wanted = set(claim_ids)
            rows = [e for e in rows if wanted.intersection(e.claim_ids)]
        return rows

    def add_claim(self, claim: Claim) -> None:
        self._save(claim)

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._get("claim", claim_id)

    def list_claims(self, project_id: str | None = None) -> list[Claim]:
        rows = self._list("claim")
        if project_id is None:
            return rows
        return [c for c in rows if c.project_id == project_id]

    def get_beliefs(self, project_id: str, as_of: datetime | None = None) -> list[Belief]:
        rows = self._list("belief")
        out = [b for b in rows if b.project_id == project_id]
        if as_of is not None:
            out = [b for b in out if b.updated_at <= as_of]
        return out

    def get_belief(self, belief_id: str) -> Belief | None:
        return self._get("belief", belief_id)

    def save_belief(self, belief: Belief, expected_version: int | None = None) -> None:
        self._save(belief, expected_version)

    def save_decision(self, decision: Decision, expected_version: int | None = None) -> None:
        self._save(decision, expected_version)

    def get_decision(self, decision_id: str) -> Decision | None:
        return self._get("decision", decision_id)

    def list_decisions(self, project_id: str | None = None) -> list[Decision]:
        rows = self._list("decision")
        if project_id is None:
            return rows
        return [d for d in rows if d.project_id == project_id]

    def save_experiment(self, experiment: Experiment, expected_version: int | None = None) -> None:
        self._save(experiment, expected_version)

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        return self._get("experiment", experiment_id)

    def list_experiments(self, project_id: str | None = None) -> list[Experiment]:
        rows = self._list("experiment")
        if project_id is None:
            return rows
        decision_ids = {d.id for d in self._list("decision") if d.project_id == project_id}
        return [e for e in rows if e.decision_id in decision_ids]

    def save_action(self, action: Action, expected_version: int | None = None) -> None:
        self._save(action, expected_version)

    def get_action(self, action_id: str) -> Action | None:
        return self._get("action", action_id)

    def list_actions(
        self,
        project_id: str | None = None,
        decision_id: str | None = None,
        experiment_id: str | None = None,
    ) -> list[Action]:
        """Public action query (P0-4). Outcomes link to actions via action_id."""
        rows = self._list("action")
        if project_id is not None:
            rows = [a for a in rows if a.project_id == project_id]
        if decision_id is not None:
            rows = [a for a in rows if a.decision_id == decision_id]
        if experiment_id is not None:
            rows = [a for a in rows if a.experiment_id == experiment_id]
        return rows

    def save_outcome(self, outcome: Outcome, expected_version: int | None = None) -> None:
        self._save(outcome, expected_version)

    def get_outcome(self, outcome_id: str) -> Outcome | None:
        return self._get("outcome", outcome_id)

    def list_outcomes(
        self,
        project_id: str | None = None,
        action_id: str | None = None,
    ) -> list[Outcome]:
        """Public outcome query (P0-4). Outcomes are keyed by ``id`` (OUT_*)
        and reference actions by ``action_id`` (ACT_*); never assume
        Outcome.id == Action.id."""
        rows = self._list("outcome")
        if action_id is not None:
            rows = [o for o in rows if o.action_id == action_id]
        if project_id is not None:
            action_ids = {a.id for a in self._list("action") if a.project_id == project_id}
            rows = [o for o in rows if o.action_id in action_ids]
        return rows

    def save_prediction(self, entry: PredictionEntry, expected_version: int | None = None) -> None:
        self._save(entry, expected_version)

    def get_prediction(self, prediction_id: str) -> PredictionEntry | None:
        return self._get("prediction", prediction_id)

    def get_open_predictions(self, project_id: str) -> list[PredictionEntry]:
        rows = self._list("prediction")
        return [p for p in rows if p.project_id == project_id and p.is_open]

    def list_predictions(self, project_id: str | None = None) -> list[PredictionEntry]:
        rows = self._list("prediction")
        if project_id is None:
            return rows
        return [p for p in rows if p.project_id == project_id]

    def resolve_prediction(self, prediction_id: str, outcome: bool) -> PredictionEntry:
        entry = self.get_prediction(prediction_id)
        if entry is None:
            raise EntityNotFoundError("prediction", prediction_id)
        updated = entry.model_copy(
            update={
                "resolution": "TRUE" if outcome else "FALSE",
                "outcome": outcome,
                "resolved_at": utcnow(),  # aware UTC (consistent with ledger path)
                "version": entry.version + 1,
            }
        )
        self.save_prediction(updated, expected_version=entry.version)
        return updated

    def save_project(self, project: Project, expected_version: int | None = None) -> None:
        self._save(project, expected_version)

    def get_project(self, project_id: str) -> Project | None:
        return self._get("project", project_id)

    def list_projects(self, user_id: str | None = None) -> list[Project]:
        rows = self._list("project")
        if user_id is None:
            return rows
        return [p for p in rows if p.user_id == user_id]

    def save_objective(self, objective: Objective, expected_version: int | None = None) -> None:
        self._save(objective, expected_version)

    def get_objective(self, objective_id: str) -> Objective | None:
        return self._get("objective", objective_id)

    def save_founder_profile(self, profile: FounderProfile, expected_version: int | None = None) -> None:
        self._save(profile, expected_version)

    def get_founder_profile(self, user_id: str) -> FounderProfile | None:
        for row in self._list_all("founder_profile"):
            profile = self.entity_types["founder_profile"].model_validate(row)
            if profile.user_id == user_id:
                return profile
        return None

    def save_financial_snapshot(self, fs: FinancialSnapshot, expected_version: int | None = None) -> None:
        self._save(fs, expected_version)

    def list_financial_snapshots(self, project_id: str) -> list[FinancialSnapshot]:
        return [f for f in self._list("financial_snapshot") if f.project_id == project_id]

    def save_company_case(self, case: CompanyCase, expected_version: int | None = None) -> None:
        self._save(case, expected_version)

    def get_company_case(self, company_id: str) -> CompanyCase | None:
        return self._get("company_case", company_id)

    def list_company_cases(self) -> list[CompanyCase]:
        return self._list("company_case")

    def save_memory(self, memory: MemoryRecord, expected_version: int | None = None) -> None:
        self._save(memory, expected_version)

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        return self._get("memory", memory_id)

    def save_portfolio(self, portfolio: FounderOpportunityPortfolio) -> None:
        self._save(portfolio)

    def get_portfolio(self, user_id: str) -> FounderOpportunityPortfolio | None:
        for row in self._list_all("portfolio"):
            portfolio = self.entity_types["portfolio"].model_validate(row)
            if portfolio.user_id == user_id:
                return portfolio
        return None

    def get_rules(self, kind: RuleKind | None = None) -> list[Rule]:
        rows = self._list("rule")
        if kind is None:
            return rows
        wanted = kind.value if hasattr(kind, "value") else str(kind)
        return [r for r in rows if r.kind == wanted or r.kind == kind]

    def save_rule(self, rule: Rule) -> None:
        self._save(rule)

    def append_event(self, event: DomainEvent) -> None:
        self._append_event(event)

    def events_since(self, after_seq: int) -> list[DomainEvent]:
        return self._events_since(after_seq)

    def in_transaction(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` inside a transaction with depth counting (P2-17).

        Nested ``in_transaction`` calls share the outermost backend
        transaction: only depth==0 delegates to the backend ``_txn`` (which
        owns BEGIN/COMMIT/ROLLBACK); inner frames just execute ``fn`` so the
        backend ``_store``/``_append_event`` do NOT commit early inside the
        batch.
        """
        depth = getattr(self, "_txn_depth", 0)
        self._txn_depth = depth + 1
        try:
            if depth == 0:
                self._txn(fn)
            else:
                fn()
        finally:
            self._txn_depth = depth

    # -- v1.1 claim binding -----------------------------------------------------

    def save_binding(
        self, binding: EvidenceClaimBinding, expected_version: int | None = None
    ) -> None:
        self._save(binding, expected_version)

    def get_binding(self, binding_id: str) -> EvidenceClaimBinding | None:
        return self._get("binding", binding_id)

    def _binding_by_id(self, binding_id: str) -> EvidenceClaimBinding | None:  # pragma: no cover
        return self._get("binding", binding_id)

    def list_bindings(
        self,
        evidence_id: str | None = None,
        claim_id: str | None = None,
        status: str | None = None,
    ) -> list[EvidenceClaimBinding]:
        rows = self._list("binding")
        if evidence_id is not None:
            rows = [b for b in rows if b.evidence_id == evidence_id]
        if claim_id is not None:
            rows = [b for b in rows if b.claim_id == claim_id]
        if status is not None:
            rows = [b for b in rows if b.status == status or b.status.value == status]
        return rows

    def save_candidate_claim(
        self, candidate: CandidateClaim, expected_version: int | None = None
    ) -> None:
        self._save(candidate, expected_version)

    def list_candidate_claims(self, validation_status: str | None = None) -> list[CandidateClaim]:
        rows = self._list("candidate_claim")
        if validation_status is not None:
            rows = [c for c in rows if c.validation_status == validation_status]
        return rows

    # -- v1.1 belief update records ---------------------------------------------

    def save_belief_update_record(self, record: BeliefUpdateRecord) -> None:
        self._save(record)

    def list_belief_update_records(self, belief_id: str) -> list[BeliefUpdateRecord]:
        rows = self._list("belief_update_record")
        return [r for r in rows if r.belief_id == belief_id]

    # -- v1.1 research ------------------------------------------------------------

    def save_research_plan(self, plan: ResearchPlan) -> None:
        self._save(plan)

    def get_research_plan(self, plan_id: str) -> ResearchPlan | None:
        return self._get("research_plan", plan_id)

    def list_research_plans(self, decision_id: str) -> list[ResearchPlan]:
        return [p for p in self._list("research_plan") if p.decision_id == decision_id]

    def save_research_trace(self, trace: ResearchTrace) -> None:
        self._save(trace)

    def list_research_traces(self, decision_id: str) -> list[ResearchTrace]:
        return [t for t in self._list("research_trace") if t.decision_id == decision_id]

    # -- v1.1 decision trace / sensitivity ------------------------------------------

    def save_decision_trace(self, trace: DecisionTrace) -> None:
        self._save(trace)

    def get_decision_trace(self, decision_id: str) -> DecisionTrace | None:
        for row in self._list("decision_trace"):
            trace = DecisionTrace.model_validate(row)
            if trace.decision_id == decision_id:
                return trace
        return None

    def save_decision_sensitivity(
        self, sensitivity: DecisionSensitivity, expected_version: int | None = None
    ) -> None:
        self._save(sensitivity, expected_version)

    def get_decision_sensitivity(self, decision_id: str) -> DecisionSensitivity | None:
        for row in self._list("decision_sensitivity"):
            sensitivity = DecisionSensitivity.model_validate(row)
            if sensitivity.decision_id == decision_id:
                return sensitivity
        return None

    # -- v1.1 evidence conflict ------------------------------------------------------

    def save_evidence_conflict(
        self, conflict: EvidenceConflict, expected_version: int | None = None
    ) -> None:
        self._save(conflict, expected_version)

    def list_evidence_conflicts(self, claim_id: str | None = None) -> list[EvidenceConflict]:
        rows = self._list("evidence_conflict")
        if claim_id is not None:
            rows = [c for c in rows if c.claim_id == claim_id]
        return rows

    # -- v1.1 observability -----------------------------------------------------------

    def save_call_record(self, record: ProviderCallRecord) -> None:
        self._save(record)

    def list_call_records(
        self, kind: str | None = None, since: datetime | None = None
    ) -> list[ProviderCallRecord]:
        rows = self._list("call_record")
        if kind is not None:
            rows = [r for r in rows if r.kind == kind]
        if since is not None:
            rows = [r for r in rows if r.started_at >= since]
        return rows

    # -- v1.2 decision ledger (V-2) ------------------------------------------------

    def save_decision_record(
        self, record: DecisionRecord, expected_version: int | None = None
    ) -> None:
        self._save(record, expected_version)

    def get_decision_record(self, decision_id: str) -> DecisionRecord | None:
        for record in self._list("decision_record"):
            if record.decision_id == decision_id:
                return record
        return None

    def list_decision_records(self, project_id: str | None = None) -> list[DecisionRecord]:
        rows = self._list("decision_record")
        if project_id is None:
            return rows
        return [r for r in rows if r.project_id == project_id]

    def save_decision_outcome_record(self, record: DecisionOutcomeRecord) -> None:
        self._save(record)

    def list_decision_outcome_records(
        self, decision_record_id: str
    ) -> list[DecisionOutcomeRecord]:
        return [
            r
            for r in self._list("decision_outcome_record")
            if r.decision_record_id == decision_record_id
        ]
