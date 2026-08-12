"""Domain base: shared model config, helpers, and public enums.

All domain objects inherit :class:`VencertiaBaseModel` (pydantic v2) which
forbids extra fields, validates on assignment, uses enum values (plain strings)
and strips whitespace — the canonical contract per docs/domain-model.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class VencertiaBaseModel(BaseModel):
    """Base pydantic model for every Vencertia domain object."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Public enums (docs/domain-model.md §1)
# ---------------------------------------------------------------------------


class Scope(str, Enum):
    FOUNDER = "FOUNDER"
    PROJECT = "PROJECT"
    CUSTOMER = "CUSTOMER"
    MARKET = "MARKET"
    COMPANY_CASE = "COMPANY_CASE"
    WORLD = "WORLD"


class EvidenceType(str, Enum):
    REAL_PAYMENT = "REAL_PAYMENT"
    CONTRACT = "CONTRACT"
    OBSERVED_BEHAVIOR = "OBSERVED_BEHAVIOR"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    CUSTOMER_COMMITMENT = "CUSTOMER_COMMITMENT"
    OFFICIAL_DATA = "OFFICIAL_DATA"
    PRIMARY_RESEARCH = "PRIMARY_RESEARCH"
    REVIEWED_EXTERNAL_RESEARCH = "REVIEWED_EXTERNAL_RESEARCH"
    ELIGIBLE_EXTERNAL_CASE_FACT = "ELIGIBLE_EXTERNAL_CASE_FACT"
    COMPANY_CASE_FACT = "COMPANY_CASE_FACT"
    FOUNDER_STATEMENT = "FOUNDER_STATEMENT"
    EXPERT_INPUT = "EXPERT_INPUT"
    LLM_INFERENCE = "LLM_INFERENCE"
    MODEL_PRIOR = "MODEL_PRIOR"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"


class AuthorityLevel(str, Enum):
    """Evidence authority hierarchy (versioned, docs/evidence-policy.md).

    Larger weight means higher authority.
    """

    PROJECT_REALITY = "PROJECT_REALITY"  # 1.00
    PROJECT_DIRECT_BEHAVIOR = "PROJECT_DIRECT_BEHAVIOR"  # 0.95
    PROJECT_EXPERIMENT_RESULT = "PROJECT_EXPERIMENT_RESULT"  # 0.90
    CUSTOMER_COMMITMENT_OR_PAYMENT = "CUSTOMER_COMMITMENT_OR_PAYMENT"  # 0.88
    ELIGIBLE_EXTERNAL_CASE_FACT = "ELIGIBLE_EXTERNAL_CASE_FACT"  # 0.75
    REVIEWED_EXTERNAL_RESEARCH = "REVIEWED_EXTERNAL_RESEARCH"  # 0.65
    FOUNDER_STATEMENT = "FOUNDER_STATEMENT"  # 0.45
    LLM_INFERENCE = "LLM_INFERENCE"  # 0.20
    MODEL_PRIOR = "MODEL_PRIOR"  # 0.10


class Verification(str, Enum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    ASSUMED = "ASSUMED"
    UNKNOWN = "UNKNOWN"


class Direction(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class ConflictStatus(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    CONFLICTED = "CONFLICTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ClaimType(str, Enum):
    FACT = "FACT"
    ESTIMATE = "ESTIMATE"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    LESSON = "LESSON"
    CAUSAL_CLAIM = "CAUSAL_CLAIM"


class ClaimStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class UpdateMethod(str, Enum):
    BETA_BERNOULLI = "BETA_BERNOULLI"
    WEIGHTED_LOG_ODDS = "WEIGHTED_LOG_ODDS"


class DecisionType(str, Enum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    HOLD = "HOLD"
    PIVOT = "PIVOT"
    KILL = "KILL"
    SELECT_OPTION = "SELECT_OPTION"
    ABSTAIN = "ABSTAIN"


class ConvergenceStatus(str, Enum):
    NOT_CONVERGED = "NOT_CONVERGED"
    RESEARCH_MORE = "RESEARCH_MORE"
    EXPERIMENT_REQUIRED = "EXPERIMENT_REQUIRED"
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
    CONDITIONALLY_CONVERGED = "CONDITIONALLY_CONVERGED"
    CONVERGED = "CONVERGED"
    EXECUTE = "EXECUTE"


class ExperimentStatus(str, Enum):
    PROPOSED = "PROPOSED"
    RUNNING = "RUNNING"
    RESOLVED_SUPPORT = "RESOLVED_SUPPORT"
    RESOLVED_REFUTE = "RESOLVED_REFUTE"
    RESOLVED_AMBIGUOUS = "RESOLVED_AMBIGUOUS"
    ABANDONED = "ABANDONED"


class PredictionResolution(str, Enum):
    OPEN = "OPEN"
    TRUE = "TRUE"
    FALSE = "FALSE"
    CANCELLED = "CANCELLED"


class ActionStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OutcomeType(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    NOISE = "NOISE"


class RuleKind(str, Enum):
    INVARIANT = "INVARIANT"
    POLICY = "POLICY"
    HEURISTIC = "HEURISTIC"
