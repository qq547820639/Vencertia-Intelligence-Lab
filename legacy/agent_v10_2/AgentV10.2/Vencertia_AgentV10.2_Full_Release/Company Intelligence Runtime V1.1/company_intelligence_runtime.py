from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


# ---------------------------------------------------------------------------
# Base contract
# ---------------------------------------------------------------------------

NonEmptyStr = Annotated[str, Field(min_length=1)]
CompanyId = Annotated[str, Field(pattern=r"^CMP[0-9A-Za-z_-]+$")]
SnapshotId = Annotated[str, Field(pattern=r"^BM[0-9A-Za-z_-]+$")]
ClaimId = Annotated[str, Field(pattern=r"^C[0-9A-Za-z_-]+$")]
EvidenceId = Annotated[str, Field(pattern=r"^E[0-9A-Za-z_-]+$")]
SourceId = Annotated[str, Field(pattern=r"^S[0-9A-Za-z_-]+$")]
ProjectId = Annotated[str, Field(min_length=1)]
FounderId = Annotated[str, Field(pattern=r"^FDR[0-9A-Za-z_-]+$")]
FundingRoundId = Annotated[str, Field(pattern=r"^FR[0-9A-Za-z_-]+$")]


class VencertiaBaseModel(BaseModel):
    """Canonical boundary model.

    Business state is closed by default: undeclared fields are rejected to avoid
    silent schema drift. Models serialize enums using their string values.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AccessClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    LICENSED = "LICENSED"
    RESTRICTED = "RESTRICTED"


class ActorType(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    RESEARCHER = "RESEARCHER"
    ADMIN = "ADMIN"


class IngestionMode(StrEnum):
    CREATE_ONLY = "CREATE_ONLY"
    UPDATE_EXISTING = "UPDATE_EXISTING"
    CREATE_OR_UPDATE = "CREATE_OR_UPDATE"
    DRY_RUN = "DRY_RUN"


class ReviewPolicy(StrEnum):
    ALWAYS_REVIEW = "ALWAYS_REVIEW"
    REVIEW_ON_CONFLICT = "REVIEW_ON_CONFLICT"
    AUTO_COMMIT_IF_VALID = "AUTO_COMMIT_IF_VALID"


class IngestionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    SCHEMA_VALIDATED = "SCHEMA_VALIDATED"
    ENTITY_RESOLVED = "ENTITY_RESOLVED"
    DIFF_READY = "DIFF_READY"
    READY_TO_COMMIT = "READY_TO_COMMIT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMMITTED = "COMMITTED"
    INDEX_GENERATED = "INDEX_GENERATED"
    ELIGIBILITY_EVALUATED = "ELIGIBILITY_EVALUATED"
    AVAILABLE = "AVAILABLE"
    PARSE_FAILED = "PARSE_FAILED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    ENTITY_AMBIGUOUS = "ENTITY_AMBIGUOUS"
    CONFLICT_BLOCKED = "CONFLICT_BLOCKED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class EntityResolutionStatus(StrEnum):
    NEW_ENTITY = "NEW_ENTITY"
    MATCHED = "MATCHED"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"


class MutationType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    SUPERSEDE = "SUPERSEDE"
    DEPRECATE = "DEPRECATE"
    CONFLICT = "CONFLICT"
    NO_CHANGE = "NO_CHANGE"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CaseRole(StrEnum):
    SUCCESS = "SUCCESS"
    DURABLE_PROFIT = "DURABLE_PROFIT"
    FAILURE = "FAILURE"
    PIVOT = "PIVOT"
    RESTRUCTURING = "RESTRUCTURING"
    BENCHMARK = "BENCHMARK"
    ADJACENT = "ADJACENT"
    ANTI_PATTERN = "ANTI_PATTERN"


class RetrievalObjective(StrEnum):
    GENERAL_RECOMMENDATION = "GENERAL_RECOMMENDATION"
    MARKET_PATTERN = "MARKET_PATTERN"
    BUSINESS_MODEL = "BUSINESS_MODEL"
    INITIAL_WEDGE = "INITIAL_WEDGE"
    EARLY_GTM = "EARLY_GTM"
    SCALED_GTM = "SCALED_GTM"
    PRICING = "PRICING"
    FINANCIAL_BENCHMARK = "FINANCIAL_BENCHMARK"
    CASHFLOW = "CASHFLOW"
    CONTRACT_RISK = "CONTRACT_RISK"
    DELIVERY_MODEL = "DELIVERY_MODEL"
    OPERATING_LEVERAGE = "OPERATING_LEVERAGE"
    RETENTION_GROWTH = "RETENTION_GROWTH"
    FAILURE_PATTERN = "FAILURE_PATTERN"
    ANTI_PATTERN = "ANTI_PATTERN"
    PIVOT_PATTERN = "PIVOT_PATTERN"
    RESTRUCTURING_PATTERN = "RESTRUCTURING_PATTERN"
    COMPANY_DEEP_DIVE = "COMPANY_DEEP_DIVE"
    COMPETITIVE_CASE_SET = "COMPETITIVE_CASE_SET"
    FOUNDER_MARKET_FIT = "FOUNDER_MARKET_FIT"


class CaseVerdict(StrEnum):
    HIGHLY_RELEVANT = "HIGHLY_RELEVANT"
    RELEVANT = "RELEVANT"
    ADJACENT = "ADJACENT"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    WEAK_REFERENCE = "WEAK_REFERENCE"
    DO_NOT_USE = "DO_NOT_USE"


class TransferabilityLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MatchStrength(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FactStatus(StrEnum):
    NOT_READY = "NOT_READY"
    FACT_READY = "FACT_READY"
    FACT_VERIFIED = "FACT_VERIFIED"


class IntelligenceStatus(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    GENERATED = "GENERATED"
    INTELLIGENCE_REVIEWED = "INTELLIGENCE_REVIEWED"


class ClaimStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    CONFLICTED = "CONFLICTED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class SourceQuality(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    AGING = "AGING"
    STALE = "STALE"
    NOT_TIME_SENSITIVE = "NOT_TIME_SENSITIVE"


class CaseDepth(StrEnum):
    CASE_UNIT = "CASE_UNIT"
    FULL_CASE = "FULL_CASE"


class UpdateProposalStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY_TO_COMMIT = "READY_TO_COMMIT"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"


class ConflictResolutionAction(StrEnum):
    ACCEPT_EXISTING = "ACCEPT_EXISTING"
    ACCEPT_INCOMING = "ACCEPT_INCOMING"
    KEEP_CONFLICTED = "KEEP_CONFLICTED"
    SUPERSEDE_BOTH = "SUPERSEDE_BOTH"


# ---------------------------------------------------------------------------
# Common structures
# ---------------------------------------------------------------------------

class ActorRef(VencertiaBaseModel):
    actor_type: ActorType
    actor_id: NonEmptyStr


class CaseUnitRef(VencertiaBaseModel):
    """The canonical comparison unit: company x snapshot x scope."""

    company_id: CompanyId
    snapshot_id: SnapshotId
    operating_segment_ids: list[NonEmptyStr] = Field(default_factory=list)
    business_unit_id: str | None = None
    offer_ids: list[NonEmptyStr] = Field(default_factory=list)
    revenue_stream_ids: list[NonEmptyStr] = Field(default_factory=list)
    customer_segment_ids: list[NonEmptyStr] = Field(default_factory=list)
    geography: list[NonEmptyStr] = Field(default_factory=list)
    valid_period: str | None = None


class RuntimeMetadata(VencertiaBaseModel):
    ingestion_id: NonEmptyStr
    revision_id: NonEmptyStr
    parser_version: NonEmptyStr
    schema_version: NonEmptyStr
    source_file_ref: NonEmptyStr
    source_file_hash: NonEmptyStr
    record_content_hash: NonEmptyStr
    uploaded_at: datetime
    uploaded_by: ActorRef
    committed_at: datetime | None = None
    committed_by: ActorRef | None = None
    previous_revision_id: str | None = None
    mutation_reason: str | None = None
    access_class: AccessClass = AccessClass.INTERNAL
    state_version: int = Field(default=1, ge=1)


class ValidationIssue(VencertiaBaseModel):
    path: NonEmptyStr
    message: NonEmptyStr
    severity: Severity
    code: str | None = None


class ConflictItem(VencertiaBaseModel):
    path: NonEmptyStr
    existing_value: object | None = None
    incoming_value: object | None = None
    severity: Severity
    claim_ids: list[ClaimId] = Field(default_factory=list)
    resolution_required: bool = True


class DiffSummary(VencertiaBaseModel):
    added: int = Field(default=0, ge=0)
    changed: int = Field(default=0, ge=0)
    removed: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)


class EntityResolutionResult(VencertiaBaseModel):
    status: EntityResolutionStatus
    company_id: CompanyId | None = None
    confidence: Confidence
    candidate_company_ids: list[CompanyId] = Field(default_factory=list)
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_company_resolution(self):
        if self.status in {EntityResolutionStatus.MATCHED, EntityResolutionStatus.NEW_ENTITY} and not self.company_id:
            raise ValueError("company_id is required for MATCHED or NEW_ENTITY")
        return self


# ---------------------------------------------------------------------------
# V1.1 compatibility domain extensions
# ---------------------------------------------------------------------------

class SourceMetadataExtension(VencertiaBaseModel):
    language: str | None = None
    publisher_country: str | None = None
    source_geography: list[NonEmptyStr] = Field(default_factory=list)
    canonical_url: HttpUrl | None = None


class FounderRecord(VencertiaBaseModel):
    """Public company-case founder intelligence restored from the V9 contract.

    This is NOT user Founder Memory and must only contain case-intelligence data
    whose provenance can be traced through Claim/Evidence/Source.
    """
    founder_id: FounderId
    company_id: CompanyId
    name: NonEmptyStr
    education: list[NonEmptyStr] = Field(default_factory=list)
    previous_companies: list[NonEmptyStr] = Field(default_factory=list)
    previous_industries: list[NonEmptyStr] = Field(default_factory=list)
    previous_startups: list[NonEmptyStr] = Field(default_factory=list)
    technical_background: str | None = None
    sales_background: str | None = None
    industry_background: str | None = None
    capital_background: str | None = None
    special_resources: list[NonEmptyStr] = Field(default_factory=list)
    founder_market_fit_notes: str | None = None
    claim_ids: list[ClaimId] = Field(default_factory=list)
    last_verified_at: datetime | None = None
    record_scope: Literal["PUBLIC_CASE_INTELLIGENCE"] = "PUBLIC_CASE_INTELLIGENCE"


class FundingRound(VencertiaBaseModel):
    """Structured funding event. Funding is context, never proof of demand."""
    funding_round_id: FundingRoundId
    company_id: CompanyId
    round_name: NonEmptyStr
    announced_at: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    investors: list[NonEmptyStr] = Field(default_factory=list)
    lead_investors: list[NonEmptyStr] = Field(default_factory=list)
    pre_money_valuation: Decimal | None = Field(default=None, ge=0)
    post_money_valuation: Decimal | None = Field(default=None, ge=0)
    total_funding_after_round: Decimal | None = Field(default=None, ge=0)
    claim_ids: list[ClaimId] = Field(default_factory=list)
    source_ids: list[SourceId] = Field(default_factory=list)
    last_verified_at: datetime | None = None

# ---------------------------------------------------------------------------
# Ingestion contracts
# ---------------------------------------------------------------------------

class IngestCaseRequest(VencertiaBaseModel):
    operation: Literal["INGEST_COMPANY_CASE"] = "INGEST_COMPANY_CASE"
    file_ref: NonEmptyStr
    template_family: Literal["Startup Intelligence Company Case"] = "Startup Intelligence Company Case"
    declared_schema_version: NonEmptyStr
    mode: IngestionMode = IngestionMode.CREATE_OR_UPDATE
    review_policy: ReviewPolicy = ReviewPolicy.REVIEW_ON_CONFLICT
    requested_by: ActorRef
    access_class: AccessClass = AccessClass.INTERNAL
    idempotency_key: NonEmptyStr
    expected_company_state_version: int | None = Field(default=None, ge=1)


class IngestCaseResult(VencertiaBaseModel):
    ingestion_id: NonEmptyStr
    status: IngestionStatus
    detected_schema_version: str | None = None
    entity_resolution: EntityResolutionResult | None = None
    schema_valid: bool = False
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    diff: DiffSummary | None = None
    conflicts: list[ConflictItem] = Field(default_factory=list)
    proposed_action: MutationType | None = None
    company_id: CompanyId | None = None
    revision_id: str | None = None
    output_state_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_result_state(self):
        if self.status in {IngestionStatus.COMMITTED, IngestionStatus.INDEX_GENERATED,
                           IngestionStatus.ELIGIBILITY_EVALUATED, IngestionStatus.AVAILABLE}:
            if not self.company_id or not self.revision_id:
                raise ValueError("committed/available ingestion must include company_id and revision_id")
        if self.schema_valid and self.errors:
            raise ValueError("schema_valid cannot be true when validation errors exist")
        return self


# ---------------------------------------------------------------------------
# Retrieval contracts
# ---------------------------------------------------------------------------

class ProjectRetrievalContext(VencertiaBaseModel):
    project_id: ProjectId
    project_stage: NonEmptyStr | None = None
    geography: list[NonEmptyStr] = Field(default_factory=list)
    customer_model: list[NonEmptyStr] = Field(default_factory=list)
    customer_segment: list[NonEmptyStr] = Field(default_factory=list)
    payer: str | None = None
    problem_tags: list[NonEmptyStr] = Field(default_factory=list)
    purchase_trigger_tags: list[NonEmptyStr] = Field(default_factory=list)
    offering_type: list[NonEmptyStr] = Field(default_factory=list)
    revenue_models: list[NonEmptyStr] = Field(default_factory=list)
    pricing_models: list[NonEmptyStr] = Field(default_factory=list)
    sales_motion: list[NonEmptyStr] = Field(default_factory=list)
    delivery_model: list[NonEmptyStr] = Field(default_factory=list)
    capital_intensity: str | None = None
    working_capital_intensity: str | None = None
    regulation_intensity: str | None = None
    founder_advantages: list[NonEmptyStr] = Field(default_factory=list)
    known_constraints: list[NonEmptyStr] = Field(default_factory=list)


class SearchCasesRequest(VencertiaBaseModel):
    operation: Literal["SEARCH_COMPANY_CASES"] = "SEARCH_COMPANY_CASES"
    retrieval_objective: RetrievalObjective
    target_context: ProjectRetrievalContext
    case_roles: list[CaseRole] = Field(default_factory=list)
    max_candidates: int = Field(default=20, ge=1, le=100)
    max_context_cases: int = Field(default=6, ge=1, le=12)
    include_counterexamples: bool = True
    require_current_data: bool = False

    @model_validator(mode="after")
    def validate_limits(self):
        if self.max_context_cases > self.max_candidates:
            raise ValueError("max_context_cases cannot exceed max_candidates")
        return self


class EligibilityFlags(VencertiaBaseModel):
    fact_ready: bool = False
    recommendation_ready: bool = False
    financial_benchmark_ready: bool = False
    failure_benchmark_ready: bool = False
    pivot_benchmark_ready: bool = False
    restructuring_benchmark_ready: bool = False
    gtm_benchmark_ready: bool = False
    pricing_benchmark_ready: bool = False


class CaseDataQuality(VencertiaBaseModel):
    fact_status: FactStatus
    intelligence_status: IntelligenceStatus
    confidence: Confidence
    completeness: Confidence
    last_verified_at: datetime | None = None


class SearchCandidate(VencertiaBaseModel):
    case_unit_ref: CaseUnitRef
    retrieval_score: float = Field(ge=0, le=1)
    objective_score: float | None = Field(default=None, ge=0, le=1)
    scope_compatible: bool
    time_compatible: bool
    eligibility: EligibilityFlags
    data_quality: CaseDataQuality
    case_roles: list[CaseRole] = Field(default_factory=list)
    short_reason: str | None = None


class SearchCasesResult(VencertiaBaseModel):
    retrieval_objective: RetrievalObjective
    candidates: list[SearchCandidate]
    retrieval_warnings: list[NonEmptyStr] = Field(default_factory=list)
    counterexample_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Comparison contracts
# ---------------------------------------------------------------------------

class DimensionMatch(VencertiaBaseModel):
    dimension: NonEmptyStr
    strength: MatchStrength
    explanation: str | None = None
    claim_ids: list[ClaimId] = Field(default_factory=list)


class CriticalDifference(VencertiaBaseModel):
    dimension: NonEmptyStr
    severity: Severity
    description: NonEmptyStr
    transfer_impact: str | None = None
    claim_ids: list[ClaimId] = Field(default_factory=list)


class TransferabilityAssessment(VencertiaBaseModel):
    level: TransferabilityLevel
    transferable: list[NonEmptyStr] = Field(default_factory=list)
    conditional: list[NonEmptyStr] = Field(default_factory=list)
    do_not_transfer: list[NonEmptyStr] = Field(default_factory=list)
    prerequisites: list[NonEmptyStr] = Field(default_factory=list)


class CompareCaseRequest(VencertiaBaseModel):
    operation: Literal["COMPARE_CASE_TO_PROJECT"] = "COMPARE_CASE_TO_PROJECT"
    project_id: ProjectId
    case_unit_ref: CaseUnitRef
    comparison_objective: RetrievalObjective


class ComparisonResult(VencertiaBaseModel):
    comparison_id: NonEmptyStr
    project_id: ProjectId
    case_unit_ref: CaseUnitRef
    comparison_objective: RetrievalObjective
    verdict: CaseVerdict
    matches: list[DimensionMatch] = Field(default_factory=list)
    critical_differences: list[CriticalDifference] = Field(default_factory=list)
    transferability: TransferabilityAssessment
    allowed_uses: list[NonEmptyStr] = Field(default_factory=list)
    prohibited_uses: list[NonEmptyStr] = Field(default_factory=list)
    limitations: list[NonEmptyStr] = Field(default_factory=list)
    confidence: Confidence

    @model_validator(mode="after")
    def no_use_overlap(self):
        overlap = set(self.allowed_uses) & set(self.prohibited_uses)
        if overlap:
            raise ValueError(f"allowed_uses and prohibited_uses overlap: {sorted(overlap)}")
        if self.verdict == CaseVerdict.DO_NOT_USE and self.allowed_uses:
            raise ValueError("DO_NOT_USE comparison cannot contain allowed_uses")
        return self


# ---------------------------------------------------------------------------
# Context contracts
# ---------------------------------------------------------------------------

class TraceRefs(VencertiaBaseModel):
    claim_ids: list[ClaimId] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    source_ids: list[SourceId] = Field(default_factory=list)


class ContextCase(VencertiaBaseModel):
    case_unit_ref: CaseUnitRef
    one_line_case: NonEmptyStr
    verdict: CaseVerdict
    relevant_facts: list[NonEmptyStr] = Field(default_factory=list)
    similarities: list[NonEmptyStr] = Field(default_factory=list)
    critical_differences: list[NonEmptyStr] = Field(default_factory=list)
    transferable_patterns: list[NonEmptyStr] = Field(default_factory=list)
    anti_patterns: list[NonEmptyStr] = Field(default_factory=list)
    allowed_uses: list[NonEmptyStr] = Field(default_factory=list)
    prohibited_uses: list[NonEmptyStr] = Field(default_factory=list)
    data_quality: CaseDataQuality
    trace_refs: TraceRefs


class ProjectContextSummary(VencertiaBaseModel):
    project_id: ProjectId
    stage: str | None = None
    primary_bottleneck: str | None = None
    evidence_summary: list[NonEmptyStr] = Field(default_factory=list)
    constraints: list[NonEmptyStr] = Field(default_factory=list)


class CaseContextPack(VencertiaBaseModel):
    retrieval_objective: RetrievalObjective
    target_project_summary: ProjectContextSummary
    cases: list[ContextCase] = Field(default_factory=list, max_length=6)
    counterexamples: list[ContextCase] = Field(default_factory=list, max_length=3)
    cross_case_patterns: list[NonEmptyStr] = Field(default_factory=list)
    cross_case_disagreements: list[NonEmptyStr] = Field(default_factory=list)
    context_generated_at: datetime

    @model_validator(mode="after")
    def prevent_duplicate_case_units(self):
        keys: set[tuple[str, str, str, str]] = set()
        for case in [*self.cases, *self.counterexamples]:
            r = case.case_unit_ref
            key = (
                r.company_id,
                r.snapshot_id,
                r.business_unit_id or "",
                r.valid_period or "",
            )
            if key in keys:
                raise ValueError("duplicate CaseUnitRef in CaseContextPack")
            keys.add(key)
        return self


# ---------------------------------------------------------------------------
# Claim trace contracts
# ---------------------------------------------------------------------------

class ClaimTraceRequest(VencertiaBaseModel):
    operation: Literal["GET_CLAIM_TRACE"] = "GET_CLAIM_TRACE"
    company_id: CompanyId
    claim_id: ClaimId


class EvidenceTraceItem(VencertiaBaseModel):
    evidence_id: EvidenceId
    source_id: SourceId
    evidence_type: NonEmptyStr
    directness: Literal["DIRECT", "INDIRECT"]
    source_quality: SourceQuality
    freshness: Freshness
    supports_claim: bool = False
    contradicts_claim: bool = False
    short_extract: str | None = None

    @model_validator(mode="after")
    def validate_relation(self):
        if self.supports_claim and self.contradicts_claim:
            raise ValueError("an evidence trace item cannot both support and contradict the same claim")
        return self


class ClaimTraceResult(VencertiaBaseModel):
    company_id: CompanyId
    claim_id: ClaimId
    claim_text: NonEmptyStr
    status: ClaimStatus
    confidence: Confidence
    supporting_evidence: list[EvidenceTraceItem] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceTraceItem] = Field(default_factory=list)
    last_verified_at: datetime | None = None


# ---------------------------------------------------------------------------
# V1.1 deep-dive, case-set, and incremental-update contracts
# ---------------------------------------------------------------------------

class GetCaseRequest(VencertiaBaseModel):
    operation: Literal["GET_COMPANY_CASE"] = "GET_COMPANY_CASE"
    company_id: CompanyId
    snapshot_id: SnapshotId | None = None
    depth: CaseDepth = CaseDepth.FULL_CASE
    include_founders: bool = True
    include_funding_rounds: bool = True


class GetCaseResult(VencertiaBaseModel):
    company_id: CompanyId
    canonical_case: dict[str, object] | None = None
    case_unit_refs: list[CaseUnitRef] = Field(default_factory=list)
    founders: list[FounderRecord] = Field(default_factory=list)
    funding_rounds: list[FundingRound] = Field(default_factory=list)
    data_quality: CaseDataQuality | None = None
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class CompareCaseSetRequest(VencertiaBaseModel):
    operation: Literal["COMPARE_CASE_SET"] = "COMPARE_CASE_SET"
    project_id: ProjectId
    case_unit_refs: list[CaseUnitRef] = Field(min_length=2, max_length=12)
    comparison_objective: RetrievalObjective = RetrievalObjective.COMPETITIVE_CASE_SET


class CompareCaseSetResult(VencertiaBaseModel):
    comparison_set_id: NonEmptyStr
    project_id: ProjectId
    comparison_objective: RetrievalObjective
    case_results: list[ComparisonResult] = Field(min_length=2, max_length=12)
    shared_patterns: list[NonEmptyStr] = Field(default_factory=list)
    material_differences: list[NonEmptyStr] = Field(default_factory=list)
    cross_case_conflicts: list[NonEmptyStr] = Field(default_factory=list)
    strongest_counterexample: CaseUnitRef | None = None
    confidence: Confidence

    @model_validator(mode="after")
    def unique_case_units(self):
        keys = {(r.case_unit_ref.company_id, r.case_unit_ref.snapshot_id, r.case_unit_ref.business_unit_id or "", r.case_unit_ref.valid_period or "") for r in self.case_results}
        if len(keys) != len(self.case_results):
            raise ValueError("duplicate CaseUnitRef in CompareCaseSetResult")
        return self


class CasePatchOperation(VencertiaBaseModel):
    mutation_type: MutationType
    path: NonEmptyStr
    proposed_value: object | None = None
    rationale: NonEmptyStr
    claim_ids: list[ClaimId] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    source_ids: list[SourceId] = Field(default_factory=list)


class ProposeCaseUpdateRequest(VencertiaBaseModel):
    operation: Literal["PROPOSE_CASE_UPDATE"] = "PROPOSE_CASE_UPDATE"
    company_id: CompanyId
    updates: list[CasePatchOperation] = Field(min_length=1, max_length=100)
    requested_by: ActorRef
    idempotency_key: NonEmptyStr
    expected_company_state_version: int | None = Field(default=None, ge=1)


class ProposeCaseUpdateResult(VencertiaBaseModel):
    proposal_id: NonEmptyStr
    company_id: CompanyId
    status: UpdateProposalStatus
    accepted_updates: int = Field(default=0, ge=0)
    rejected_updates: int = Field(default=0, ge=0)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    revision_id: str | None = None
    output_state_version: int | None = Field(default=None, ge=1)


class RefreshCaseRequest(VencertiaBaseModel):
    operation: Literal["REFRESH_COMPANY_CASE"] = "REFRESH_COMPANY_CASE"
    company_id: CompanyId
    topics: list[NonEmptyStr] = Field(default_factory=list, max_length=30)
    reason: NonEmptyStr
    requested_by: ActorRef
    idempotency_key: NonEmptyStr


class RefreshCaseResult(VencertiaBaseModel):
    refresh_job_id: NonEmptyStr
    company_id: CompanyId
    status: UpdateProposalStatus
    topics_accepted: list[NonEmptyStr] = Field(default_factory=list)
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class SubmitEvidenceRequest(VencertiaBaseModel):
    operation: Literal["SUBMIT_CASE_EVIDENCE"] = "SUBMIT_CASE_EVIDENCE"
    company_id: CompanyId
    claim_id: ClaimId | None = None
    claim_candidate: str | None = None
    evidence_type: NonEmptyStr
    observed_or_published_date: date | None = None
    relevant_data_or_short_extract: NonEmptyStr
    supports_claim: bool = False
    contradicts_claim: bool = False
    source: SourceMetadataExtension
    requested_by: ActorRef
    idempotency_key: NonEmptyStr

    @model_validator(mode="after")
    def validate_submission(self):
        if not self.claim_id and not self.claim_candidate:
            raise ValueError("claim_id or claim_candidate is required")
        if self.supports_claim and self.contradicts_claim:
            raise ValueError("submitted evidence cannot both support and contradict the same claim")
        return self


class SubmitEvidenceResult(VencertiaBaseModel):
    submission_id: NonEmptyStr
    company_id: CompanyId
    status: UpdateProposalStatus
    claim_id: ClaimId | None = None
    evidence_id: EvidenceId | None = None
    source_id: SourceId | None = None
    warnings: list[NonEmptyStr] = Field(default_factory=list)


class ResolveCaseConflictRequest(VencertiaBaseModel):
    operation: Literal["RESOLVE_CASE_CONFLICT"] = "RESOLVE_CASE_CONFLICT"
    company_id: CompanyId
    conflict_id: NonEmptyStr
    action: ConflictResolutionAction
    rationale: NonEmptyStr
    requested_by: ActorRef
    idempotency_key: NonEmptyStr
    expected_company_state_version: int | None = Field(default=None, ge=1)


class ResolveCaseConflictResult(VencertiaBaseModel):
    company_id: CompanyId
    conflict_id: NonEmptyStr
    status: UpdateProposalStatus
    revision_id: str | None = None
    output_state_version: int | None = Field(default=None, ge=1)

# ---------------------------------------------------------------------------
# Tool envelope - optional unified boundary for tool routers
# ---------------------------------------------------------------------------

class CompanyIntelligenceToolContract(VencertiaBaseModel):
    ingest_case_request: IngestCaseRequest | None = None
    ingest_case_result: IngestCaseResult | None = None
    search_cases_request: SearchCasesRequest | None = None
    search_cases_result: SearchCasesResult | None = None
    compare_case_request: CompareCaseRequest | None = None
    comparison_result: ComparisonResult | None = None
    case_context_pack: CaseContextPack | None = None
    claim_trace_request: ClaimTraceRequest | None = None
    claim_trace_result: ClaimTraceResult | None = None
    get_case_request: GetCaseRequest | None = None
    get_case_result: GetCaseResult | None = None
    compare_case_set_request: CompareCaseSetRequest | None = None
    compare_case_set_result: CompareCaseSetResult | None = None
    propose_case_update_request: ProposeCaseUpdateRequest | None = None
    propose_case_update_result: ProposeCaseUpdateResult | None = None
    refresh_case_request: RefreshCaseRequest | None = None
    refresh_case_result: RefreshCaseResult | None = None
    submit_evidence_request: SubmitEvidenceRequest | None = None
    submit_evidence_result: SubmitEvidenceResult | None = None
    resolve_case_conflict_request: ResolveCaseConflictRequest | None = None
    resolve_case_conflict_result: ResolveCaseConflictResult | None = None


__all__ = [
    "VencertiaBaseModel",
    "CaseUnitRef",
    "RuntimeMetadata",
    "FounderRecord",
    "FundingRound",
    "SourceMetadataExtension",
    "IngestCaseRequest",
    "IngestCaseResult",
    "SearchCasesRequest",
    "SearchCasesResult",
    "CompareCaseRequest",
    "ComparisonResult",
    "CaseContextPack",
    "ClaimTraceRequest",
    "ClaimTraceResult",
    "GetCaseRequest",
    "GetCaseResult",
    "CompareCaseSetRequest",
    "CompareCaseSetResult",
    "ProposeCaseUpdateRequest",
    "ProposeCaseUpdateResult",
    "RefreshCaseRequest",
    "RefreshCaseResult",
    "SubmitEvidenceRequest",
    "SubmitEvidenceResult",
    "ResolveCaseConflictRequest",
    "ResolveCaseConflictResult",
    "CompanyIntelligenceToolContract",
]
