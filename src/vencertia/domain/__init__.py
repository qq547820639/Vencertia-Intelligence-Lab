"""Domain package — canonical contracts (docs/domain-model.md is authoritative)."""

from __future__ import annotations

from vencertia.domain.action_outcome import Action, Outcome
from vencertia.domain.base import (
    ActionStatus,
    AuthorityLevel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    ConvergenceStatus,
    DecisionType,
    Direction,
    EvidenceType,
    ExperimentStatus,
    OutcomeType,
    PredictionResolution,
    RuleKind,
    Scope,
    UpdateMethod,
    VencertiaBaseModel,
    Verification,
    utcnow,
)
from vencertia.domain.belief import Belief, ConflictAlert, EvidenceApplication
from vencertia.domain.calibration import CalibrationProfile, CalibrationScope
from vencertia.domain.claim import Claim
from vencertia.domain.company import CaseUnitRef, ClaimTrace, CompanyCase, FounderRecord, FundingRound
from vencertia.domain.convergence import ConvergenceReport, CriticalUncertainty
from vencertia.domain.decision import Decision, DecisionOption, DecisionResult, OptionScore
from vencertia.domain.evidence import Evidence, Provenance
from vencertia.domain.experiment import Experiment, RankedExperiment
from vencertia.domain.founder import (
    FounderOpportunityPortfolio,
    FounderProfile,
    FounderState,
    Opportunity,
)
from vencertia.domain.memory import (
    AccessClass,
    MemoryCandidate,
    MemoryOperation,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from vencertia.domain.objective import Objective, ObjectiveDirection
from vencertia.domain.policy import Rule, RuleSet
from vencertia.domain.prediction import PredictionEntry
from vencertia.domain.project import FinancialSnapshot, Project, ProjectKB, ProjectStatus, Stage

__all__ = [
    "Action",
    "ActionStatus",
    "AccessClass",
    "AuthorityLevel",
    "Belief",
    "CalibrationProfile",
    "CalibrationScope",
    "CaseUnitRef",
    "Claim",
    "ClaimStatus",
    "ClaimTrace",
    "ClaimType",
    "CompanyCase",
    "ConflictAlert",
    "ConflictStatus",
    "ConvergenceReport",
    "ConvergenceStatus",
    "CriticalUncertainty",
    "Decision",
    "DecisionOption",
    "DecisionResult",
    "DecisionType",
    "Direction",
    "Evidence",
    "EvidenceApplication",
    "EvidenceType",
    "Experiment",
    "ExperimentStatus",
    "FinancialSnapshot",
    "FounderOpportunityPortfolio",
    "FounderProfile",
    "FounderRecord",
    "FounderState",
    "FundingRound",
    "MemoryCandidate",
    "MemoryOperation",
    "MemoryRecord",
    "MemoryScope",
    "MemoryStatus",
    "MemoryType",
    "Objective",
    "ObjectiveDirection",
    "OptionScore",
    "Opportunity",
    "Outcome",
    "OutcomeType",
    "PredictionEntry",
    "PredictionResolution",
    "Project",
    "ProjectKB",
    "ProjectStatus",
    "Provenance",
    "RankedExperiment",
    "Rule",
    "RuleKind",
    "RuleSet",
    "Scope",
    "Stage",
    "UpdateMethod",
    "VencertiaBaseModel",
    "Verification",
    "utcnow",
]
