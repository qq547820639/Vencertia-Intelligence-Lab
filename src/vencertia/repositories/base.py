"""Repository contracts and errors.

The repository layer is the ONLY state-mutation entry point (ADR-002).
Every write uses optimistic locking: callers load an object, mutate it, then
save with the expected version. A stale write raises :class:`StaleWriteError`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, ClassVar, Protocol, TypeVar, runtime_checkable

from vencertia.domain import (
    Action,
    Belief,
    Claim,
    CompanyCase,
    Decision,
    Evidence,
    Experiment,
    FinancialSnapshot,
    FounderOpportunityPortfolio,
    FounderProfile,
    MemoryRecord,
    Objective,
    Outcome,
    PredictionEntry,
    Project,
    Rule,
    RuleKind,
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
    def add_evidence(self, evidence: Evidence) -> None: ...
    def get_evidence(self, evidence_id: str) -> Evidence | None: ...
    def list_evidence(self, claim_ids: list[str] | None = None) -> list[Evidence]: ...
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
    def save_outcome(self, outcome: Outcome, expected_version: int | None = None) -> None: ...
    def get_outcome(self, outcome_id: str) -> Outcome | None: ...

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

    def add_evidence(self, evidence: Evidence) -> None:
        self._save(evidence)

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self._get("evidence", evidence_id)

    def list_evidence(self, claim_ids: list[str] | None = None) -> list[Evidence]:
        rows = self._list("evidence")
        if claim_ids is None:
            return rows
        wanted = set(claim_ids)
        return [e for e in rows if wanted.intersection(e.claim_ids)]

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

    def save_outcome(self, outcome: Outcome, expected_version: int | None = None) -> None:
        self._save(outcome, expected_version)

    def get_outcome(self, outcome_id: str) -> Outcome | None:
        return self._get("outcome", outcome_id)

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
        self._txn(fn)
