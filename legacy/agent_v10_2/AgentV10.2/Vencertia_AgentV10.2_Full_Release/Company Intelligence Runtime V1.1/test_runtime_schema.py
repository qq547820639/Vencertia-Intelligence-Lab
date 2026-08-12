from datetime import datetime, timezone
from pydantic import ValidationError
import pytest

from company_intelligence_runtime import (
    ActorRef, CaseContextPack, CaseDataQuality, CaseUnitRef, CaseVerdict,
    ComparisonResult, Confidence, ContextCase, FactStatus, IngestCaseRequest,
    IntelligenceStatus, ProjectContextSummary, RetrievalObjective, SearchCasesRequest,
    TransferabilityAssessment, TransferabilityLevel, TraceRefs, FounderRecord, FundingRound,
    CompareCaseSetRequest, ProposeCaseUpdateRequest, CasePatchOperation, MutationType,
    SubmitEvidenceRequest, SourceMetadataExtension
)

def case_ref(i="001"):
    return CaseUnitRef(company_id=f"CMP{i}", snapshot_id=f"BM{i}", business_unit_id="BU001", valid_period="2025-01-01/2025-12-31")

def quality():
    return CaseDataQuality(fact_status=FactStatus.FACT_VERIFIED, intelligence_status=IntelligenceStatus.INTELLIGENCE_REVIEWED, confidence=Confidence.HIGH, completeness=Confidence.HIGH)

def test_ingest_requires_idempotency_key():
    with pytest.raises(ValidationError):
        IngestCaseRequest(file_ref="file_1", declared_schema_version="1.4", requested_by=ActorRef(actor_type="USER", actor_id="USR001"))

def test_search_context_limit_cannot_exceed_candidates():
    with pytest.raises(ValidationError):
        SearchCasesRequest(retrieval_objective=RetrievalObjective.EARLY_GTM, target_context={"project_id": "PRJ001"}, max_candidates=3, max_context_cases=6)

def test_do_not_use_cannot_have_allowed_uses():
    with pytest.raises(ValidationError):
        ComparisonResult(comparison_id="CCMP001", project_id="PRJ001", case_unit_ref=case_ref(), comparison_objective=RetrievalObjective.EARLY_GTM, verdict=CaseVerdict.DO_NOT_USE, transferability=TransferabilityAssessment(level=TransferabilityLevel.LOW), allowed_uses=["EARLY_GTM_PATTERN"], confidence=Confidence.LOW)

def test_duplicate_case_units_rejected_in_context_pack():
    c=ContextCase(case_unit_ref=case_ref(), one_line_case="Example company", verdict=CaseVerdict.RELEVANT, data_quality=quality(), trace_refs=TraceRefs())
    with pytest.raises(ValidationError):
        CaseContextPack(retrieval_objective=RetrievalObjective.EARLY_GTM, target_project_summary=ProjectContextSummary(project_id="PRJ001"), cases=[c], counterexamples=[c], context_generated_at=datetime.now(timezone.utc))

def test_v11_retrieval_objectives_exist():
    assert RetrievalObjective.COMPANY_DEEP_DIVE.value == "COMPANY_DEEP_DIVE"
    assert RetrievalObjective.COMPETITIVE_CASE_SET.value == "COMPETITIVE_CASE_SET"
    assert RetrievalObjective.FOUNDER_MARKET_FIT.value == "FOUNDER_MARKET_FIT"

def test_founder_record_is_public_case_intelligence():
    f=FounderRecord(founder_id="FDR001", company_id="CMP001", name="Example Founder")
    assert f.record_scope == "PUBLIC_CASE_INTELLIGENCE"

def test_funding_round_structured_record():
    r=FundingRound(funding_round_id="FR001", company_id="CMP001", round_name="Seed", amount=1000000, currency="USD")
    assert str(r.amount) == "1000000"

def test_compare_case_set_requires_two_units():
    with pytest.raises(ValidationError):
        CompareCaseSetRequest(project_id="PRJ001", case_unit_refs=[case_ref()])

def test_incremental_update_requires_idempotency():
    with pytest.raises(ValidationError):
        ProposeCaseUpdateRequest(company_id="CMP001", updates=[CasePatchOperation(mutation_type=MutationType.UPDATE, path="pricing.PR001", proposed_value=10, rationale="new source")], requested_by=ActorRef(actor_type="AGENT", actor_id="A8"))

def test_submit_evidence_requires_claim_target():
    with pytest.raises(ValidationError):
        SubmitEvidenceRequest(company_id="CMP001", evidence_type="WEBSITE", relevant_data_or_short_extract="new price", source=SourceMetadataExtension(language="en"), requested_by=ActorRef(actor_type="AGENT", actor_id="A8"), idempotency_key="idem-1")

def test_submit_evidence_cannot_both_support_and_contradict():
    with pytest.raises(ValidationError):
        SubmitEvidenceRequest(company_id="CMP001", claim_candidate="Price changed", evidence_type="WEBSITE", relevant_data_or_short_extract="new price", supports_claim=True, contradicts_claim=True, source=SourceMetadataExtension(language="en"), requested_by=ActorRef(actor_type="AGENT", actor_id="A8"), idempotency_key="idem-2")
