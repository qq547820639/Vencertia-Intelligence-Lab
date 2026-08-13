"""Domain package — canonical contracts (docs/domain-model.md is authoritative)."""

from __future__ import annotations

from vencertia.domain.action_outcome import Action, Outcome
from vencertia.domain.base import (
    ActionState,
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
    SolveMode,
    UpdateMethod,
    VencertiaBaseModel,
    Verification,
    map_decision_type_to_action_state,
    utcnow,
)
from vencertia.domain.belief import Belief, ConflictAlert, EvidenceApplication
from vencertia.domain.belief_edge import BeliefEdge, BeliefRelationType
from vencertia.domain.belief_update import BeliefUpdateRecord
from vencertia.domain.binding import (
    BindingMethod,
    BindingStatus,
    CandidateClaim,
    ClaimBindingInput,
    ClaimBindingOutput,
    ClaimMatchResult,
    EvidenceClaimBinding,
)
from vencertia.domain.calibration import (
    CalibratedConfidence,
    CalibrationProfile,
    CalibrationScope,
    CalibrationStatus,
    EstimateType,
    classify_calibration,
)
from vencertia.domain.claim import Claim
from vencertia.domain.company import (
    CaseUnitRef,
    ClaimTrace,
    CompanyCase,
    FounderRecord,
    FundingRound,
)
from vencertia.domain.convergence import ConvergenceReport, CriticalUncertainty
from vencertia.domain.critic import (
    CritiqueFindingType,
    ModelCriticGate,
    ModelCritique,
    ModelRisk,
)
from vencertia.domain.decision import Decision, DecisionOption, DecisionResult, OptionScore
from vencertia.domain.decision_ledger import (
    CounterfactualStatus,
    DecisionOutcomeRecord,
    DecisionRecord,
)
from vencertia.domain.decision_trace import (
    BeliefContribution,
    DecisionSensitivity,
    DecisionTrace,
    FlipThreshold,
)
from vencertia.domain.evidence import Evidence, Provenance
from vencertia.domain.evidence_conflict import ConflictType, EvidenceConflict
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
from vencertia.domain.model_parameter import ApprovalStatus, ModelParameter, ProvenanceType
from vencertia.domain.objective import Objective, ObjectiveDirection
from vencertia.domain.observability import ProviderCallRecord
from vencertia.domain.policy import Rule, RuleSet
from vencertia.domain.prediction import PredictionEntry
from vencertia.domain.project import FinancialSnapshot, Project, ProjectKB, ProjectStatus, Stage
from vencertia.domain.research import (
    ResearchPlan,
    ResearchQuestion,
    ResearchStopReport,
    ResearchTrace,
)
from vencertia.domain.stakes import StakesClass, StakesProfile
from vencertia.domain.utility import UtilityComponent, UtilityRelationType

__all__ = [
    "Action",
    "ActionStatus",
    "ActionState",
    "AccessClass",
    "AuthorityLevel",
    "Belief",
    "BeliefContribution",
    "BeliefEdge",
    "BeliefRelationType",
    "BeliefUpdateRecord",
    "BindingMethod",
    "BindingStatus",
    "CalibratedConfidence",
    "CalibrationProfile",
    "CalibrationScope",
    "CandidateClaim",
    "CaseUnitRef",
    "Claim",
    "ClaimBindingInput",
    "ClaimBindingOutput",
    "ClaimMatchResult",
    "ClaimStatus",
    "ClaimTrace",
    "ClaimType",
    "CompanyCase",
    "ConflictAlert",
    "ConflictStatus",
    "ConflictType",
    "ConvergenceReport",
    "ConvergenceStatus",
    "CriticalUncertainty",
    "Decision",
    "DecisionOption",
    "DecisionResult",
    "DecisionSensitivity",
    "DecisionTrace",
    "DecisionType",
    "Direction",
    "Evidence",
    "EvidenceApplication",
    "EvidenceClaimBinding",
    "EvidenceConflict",
    "EvidenceType",
    "Experiment",
    "ExperimentStatus",
    "FinancialSnapshot",
    "FlipThreshold",
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
    "ProviderCallRecord",
    "RankedExperiment",
    "ResearchPlan",
    "ResearchQuestion",
    "ResearchStopReport",
    "ResearchTrace",
    "Rule",
    "RuleKind",
    "RuleSet",
    "Scope",
    "SolveMode",
    "Stage",
    "UpdateMethod",
    "VencertiaBaseModel",
    "Verification",
    "utcnow",
    # v1.2 additions (M0/V-1~V-5)
    "ApprovalStatus",
    "CalibrationStatus",
    "CounterfactualStatus",
    "CritiqueFindingType",
    "DecisionOutcomeRecord",
    "DecisionRecord",
    "EstimateType",
    "ModelCriticGate",
    "ModelCritique",
    "ModelParameter",
    "ModelRisk",
    "ProvenanceType",
    "StakesClass",
    "StakesProfile",
    "UtilityComponent",
    "UtilityRelationType",
    "classify_calibration",
    "map_decision_type_to_action_state",
]
