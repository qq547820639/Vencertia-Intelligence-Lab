"""V10.2 → v1.0 mapping — pure functions (docs/migration-v10.2-to-decision-runtime.md §2).

These functions are side-effect free so they can be unit-tested and reused by
the importer, the CLI, and future runtime bridges.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from vencertia.domain import (
    AccessClass,
    AuthorityLevel,
    Claim,
    ClaimType,
    CompanyCase,
    Evidence,
    MemoryOperation,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    Provenance,
    Rule,
    RuleKind,
    Scope,
    Verification,
    utcnow,
)

MAPPING_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Enum maps (V10.2 value -> v1.0 value)
# ---------------------------------------------------------------------------

VERIFICATION_MAP: Dict[str, Verification] = {
    "VERIFIED": Verification.VERIFIED,
    "ESTIMATED": Verification.ESTIMATED,
    "ASSUMED": Verification.ASSUMED,
    "UNKNOWN": Verification.UNKNOWN,
}

MEMORY_SCOPE_MAP: Dict[str, MemoryScope] = {
    "USER_GLOBAL": MemoryScope.USER_GLOBAL,
    "PROJECT_SPECIFIC": MemoryScope.PROJECT_SPECIFIC,
}

MEMORY_TYPE_MAP: Dict[str, MemoryType] = {mt.value: mt for mt in MemoryType}

MEMORY_STATUS_MAP: Dict[str, MemoryStatus] = {ms.value: ms for ms in MemoryStatus}

MEMORY_OPERATION_MAP: Dict[str, MemoryOperation] = {mo.value: mo for mo in MemoryOperation}

ACCESS_CLASS_MAP: Dict[str, AccessClass] = {ac.value: ac for ac in AccessClass}

# ProperStore -> v1.0 canonical entity type (docs §2.1)
PROPER_STORE_MAP: Dict[str, str] = {
    "STABLE_MEMORY": "memory",
    "FOUNDER_PROFILE": "founder_profile",
    "PROJECT_KB": "project",
    "EVIDENCE_LEDGER": "evidence",
    "ASSUMPTION_LEDGER": "claim",
    "EXPERIMENT_LEDGER": "experiment",
    "ACTION_LEDGER": "action",
    "DECISION_LEDGER": "decision",
    "FINANCIAL_SNAPSHOT": "financial_snapshot",
    "CUSTOMER_FEEDBACK": "evidence",
    "STARTUP_INTELLIGENCE": "company_case",
}

# V10.2 SourceType -> v1.0 AuthorityLevel (docs §2.5)
V10_2_SOURCE_TO_AUTHORITY: Dict[str, AuthorityLevel] = {
    "REAL_PAYMENT": AuthorityLevel.PROJECT_REALITY,
    "CONTRACT": AuthorityLevel.PROJECT_REALITY,
    "OBSERVED_BEHAVIOR": AuthorityLevel.PROJECT_DIRECT_BEHAVIOR,
    "EXPERIMENT_RESULT": AuthorityLevel.PROJECT_EXPERIMENT_RESULT,
    "CUSTOMER_FEEDBACK": AuthorityLevel.CUSTOMER_COMMITMENT_OR_PAYMENT,
    "PROJECT_DECISION": AuthorityLevel.FOUNDER_STATEMENT,
    "USER_EXPLICIT_INPUT": AuthorityLevel.FOUNDER_STATEMENT,
    "USER_CORRECTION": AuthorityLevel.PROJECT_REALITY,
    "AGENT_INFERENCE": AuthorityLevel.LLM_INFERENCE,
    "DOCUMENT_CLAIM": AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    "WEB_SOURCE": AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    "SYSTEM_DERIVED": AuthorityLevel.PROJECT_REALITY,
    "TOOL_RESULT": AuthorityLevel.PROJECT_DIRECT_BEHAVIOR,
}

# V10.2 SourceType -> v1.0 EvidenceType
V10_2_SOURCE_TO_EVIDENCE_TYPE: Dict[str, str] = {
    "REAL_PAYMENT": "REAL_PAYMENT",
    "CONTRACT": "CONTRACT",
    "OBSERVED_BEHAVIOR": "OBSERVED_BEHAVIOR",
    "EXPERIMENT_RESULT": "EXPERIMENT_RESULT",
    "CUSTOMER_FEEDBACK": "CUSTOMER_COMMITMENT",
    "PROJECT_DECISION": "FOUNDER_STATEMENT",
    "USER_EXPLICIT_INPUT": "FOUNDER_STATEMENT",
    "USER_CORRECTION": "SYSTEM_DERIVED",
    "AGENT_INFERENCE": "LLM_INFERENCE",
    "DOCUMENT_CLAIM": "REVIEWED_EXTERNAL_RESEARCH",
    "WEB_SOURCE": "REVIEWED_EXTERNAL_RESEARCH",
    "SYSTEM_DERIVED": "SYSTEM_DERIVED",
    "TOOL_RESULT": "OBSERVED_BEHAVIOR",
}

# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def safe_map(mapping: Dict[str, Any], value: Any, default: Any) -> Any:
    """Map a value through a dict, falling back to ``default`` for unknowns."""
    if value is None:
        return default
    return mapping.get(value, default)


def map_verification(value: str | None) -> Verification:
    return safe_map(VERIFICATION_MAP, value, Verification.UNKNOWN)


def map_memory_scope(value: str | None) -> MemoryScope:
    return safe_map(MEMORY_SCOPE_MAP, value, MemoryScope.USER_GLOBAL)


def map_memory_type(value: str | None) -> MemoryType:
    return safe_map(MEMORY_TYPE_MAP, value, MemoryType.PROJECT_FACT)


def map_memory_status(value: str | None) -> MemoryStatus:
    return safe_map(MEMORY_STATUS_MAP, value, MemoryStatus.ACTIVE)


def map_access_class(value: str | None) -> AccessClass:
    return safe_map(ACCESS_CLASS_MAP, value, AccessClass.PRIVATE)


def authority_from_v10_2_source_type(value: str | None) -> AuthorityLevel:
    return safe_map(V10_2_SOURCE_TO_AUTHORITY, value, AuthorityLevel.LLM_INFERENCE)


def evidence_type_from_v10_2_source_type(value: str | None) -> str:
    return safe_map(V10_2_SOURCE_TO_EVIDENCE_TYPE, value, "LLM_INFERENCE")


# ---------------------------------------------------------------------------
# Object mappers
# ---------------------------------------------------------------------------


def map_memory_record(record: Dict[str, Any]) -> MemoryRecord:
    """Map a V10.2 MemoryRecord dict (1:1, enums normalized)."""
    return MemoryRecord(
        memory_id=record.get("memory_id") or record.get("id") or "",
        user_id=record.get("user_id", "unknown"),
        project_id=record.get("project_id"),
        scope=map_memory_scope(record.get("scope")),
        memory_type=map_memory_type(record.get("memory_type")),
        content=record.get("content", ""),
        structured_value=record.get("structured_value"),
        source_message_ids=list(record.get("source_message_ids") or []),
        source_entity_ids=list(record.get("source_entity_ids") or []),
        evidence_ids=list(record.get("evidence_ids") or []),
        fact_status=map_verification(record.get("fact_status")),
        confidence=record.get("confidence", "MEDIUM"),
        importance=record.get("importance", "MEDIUM"),
        status=map_memory_status(record.get("status")),
        created_at=record.get("created_at") or utcnow(),
        updated_at=record.get("updated_at") or utcnow(),
        valid_from=record.get("valid_from"),
        valid_to=record.get("valid_to"),
        supersedes_memory_id=record.get("supersedes_memory_id"),
        conflicts_with_memory_ids=list(record.get("conflicts_with_memory_ids") or []),
    )


def map_evidence(record: Dict[str, Any], claim_ids: list[str] | None = None) -> Evidence:
    """Map a V10.2 evidence dict into a v1.0 Evidence (authority derived)."""
    source_type = record.get("source_type") or record.get("evidence_type")
    return Evidence(
        id=record.get("id") or record.get("evidence_id") or "",
        claim_ids=claim_ids or list(record.get("claim_ids") or []),
        scope=Scope(record.get("scope")) if record.get("scope") else Scope.PROJECT,
        evidence_type=evidence_type_from_v10_2_source_type(source_type),
        provenance=Provenance(
            source_id=record.get("source_id"),
            source_url=record.get("source_url"),
            tool=record.get("tool"),
            actor=record.get("actor"),
            raw_extract=record.get("raw_extract"),
        ),
        source=record.get("source") or record.get("content") or "",
        directness=float(record.get("directness", 0.7)),
        reliability=float(record.get("reliability", 0.7)),
        relevance=float(record.get("relevance", 1.0)),
        strength=float(record.get("strength", 0.8)),
        supports_or_contradicts=record.get("supports_or_contradicts", "NEUTRAL"),
        independence_group=record.get("independence_group"),
        observed_at=record.get("observed_at") or utcnow(),
        authority_level=authority_from_v10_2_source_type(source_type),
        verification=map_verification(record.get("verification") or record.get("fact_status")),
        transferability=record.get("transferability"),
    )


def map_company_case(data: Dict[str, Any]) -> CompanyCase:
    """Map a V10.2 Company Case dict into a CompanyCase (canonical subset)."""
    company_id = data.get("company_id") or data.get("id") or ""
    canonical_name = (
        data.get("canonical_name")
        or data.get("name")
        or data.get("title")
        or f"company-{company_id}"
    )
    return CompanyCase(
        company_id=company_id,
        canonical_name=canonical_name,
        aliases=list(data.get("aliases") or []),
        case_roles=list(data.get("case_roles") or []),
        lifecycle_stage=data.get("lifecycle_stage", "UNKNOWN"),
        capital_stage=data.get("capital_stage", "UNKNOWN"),
        as_of=data.get("as_of"),
        overall_confidence=data.get("overall_confidence", "LOW"),
        data_completeness=data.get("data_completeness", "LOW"),
        research_status=data.get("research_status", "DRAFT"),
        claim_ids=list(data.get("claim_ids") or []),
        updated_at=data.get("updated_at") or utcnow(),
    )


def map_claim(data: Dict[str, Any], claim_id: str | None = None) -> Claim:
    """Map a V10.2 assumption/claim dict into a v1.0 Claim."""
    return Claim(
        id=claim_id or data.get("claim_id") or data.get("id") or "",
        statement=data.get("statement") or data.get("content") or "",
        scope=Scope(data.get("scope")) if data.get("scope") else Scope.PROJECT,
        claim_type=ClaimType(data.get("claim_type")) if data.get("claim_type") else ClaimType.HYPOTHESIS,
        project_id=data.get("project_id"),
        company_id=data.get("company_id"),
    )


def map_rules() -> list[Rule]:
    """Default rules inherited from V10.2 (Hard Gate / Score / validation window)."""
    return [
        Rule(
            id="RUL_HARD_GATE_SCORE",
            kind=RuleKind.POLICY,
            name="hard_gate_score",
            description="Hard gate score >= 4/5 (V10.2 S5 convergence).",
            params={"min_score": 4.0, "max_score": 5.0},
            version="1.0",
        ),
        Rule(
            id="RUL_SCORE_75",
            kind=RuleKind.POLICY,
            name="score_75",
            description="Project score >= 75 required for primary status.",
            params={"threshold": 75.0},
            version="1.0",
        ),
        Rule(
            id="RUL_VALIDATION_WINDOW",
            kind=RuleKind.HEURISTIC,
            name="validation_window_days",
            description="7-14 day validation window heuristic.",
            params={"min_days": 7, "max_days": 14},
            version="1.0",
        ),
        Rule(
            id="RUL_KILLED_NOT_PRIMARY",
            kind=RuleKind.INVARIANT,
            name="killed_not_primary",
            description="A KILLED project can never be primary; at most one primary.",
            params={},
            version="1.0",
        ),
        Rule(
            id="RUL_TRANSFERABILITY_REQUIRES_REVIEW",
            kind=RuleKind.INVARIANT,
            name="transferability_requires_review",
            description="Company-case evidence needs transferability >= 0.6 and review before affecting project beliefs.",
            params={"threshold": 0.6},
            version="1.0",
        ),
        Rule(
            id="RUL_FUNDING_NOT_DEMAND",
            kind=RuleKind.INVARIANT,
            name="funding_not_demand_evidence",
            description="Funding rounds are never demand evidence.",
            params={},
            version="1.0",
        ),
    ]


def company_id_from_filename(filename: str) -> str:
    """Derive a canonical CMP_ id from a schema filename."""
    stem = filename.replace(".schema.json", "").replace(".json", "")
    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", stem).strip("_")
    return f"CMP_{slug}"
