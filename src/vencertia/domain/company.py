"""Company case family — inherited from Company Intelligence Runtime V1.1."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class CompanyCase(VencertiaBaseModel):
    company_id: str  # CMP_...
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    case_roles: list[str] = Field(default_factory=list)  # SUCCESS/FAILURE/PIVOT/...
    lifecycle_stage: str = "UNKNOWN"
    capital_stage: str = "UNKNOWN"
    as_of: datetime | None = None
    overall_confidence: str = "LOW"
    data_completeness: str = "LOW"
    research_status: str = "DRAFT"
    claim_ids: list[str] = Field(default_factory=list)
    founder_records: list[FounderRecord] = Field(default_factory=list)
    funding_rounds: list[FundingRound] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @property
    def id(self) -> str:
        """Alias so the generic repository can address this entity."""
        return self.company_id


class CaseUnitRef(VencertiaBaseModel):
    company_id: str
    snapshot_id: str
    operating_segment_ids: list[str] = Field(default_factory=list)
    business_unit_id: str | None = None
    offer_ids: list[str] = Field(default_factory=list)
    revenue_stream_ids: list[str] = Field(default_factory=list)
    customer_segment_ids: list[str] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    valid_period: str | None = None


class FounderRecord(VencertiaBaseModel):
    founder_id: str
    company_id: str
    name: str
    education: list[str] = Field(default_factory=list)
    previous_companies: list[str] = Field(default_factory=list)
    previous_industries: list[str] = Field(default_factory=list)
    previous_startups: list[str] = Field(default_factory=list)
    technical_background: str | None = None
    sales_background: str | None = None
    industry_background: str | None = None
    capital_background: str | None = None
    special_resources: list[str] = Field(default_factory=list)
    founder_market_fit_notes: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    last_verified_at: datetime | None = None


class FundingRound(VencertiaBaseModel):
    funding_round_id: str
    company_id: str
    round_name: str
    announced_at: date | None = None
    amount: float | None = None
    currency: str | None = None
    investors: list[str] = Field(default_factory=list)
    lead_investors: list[str] = Field(default_factory=list)
    pre_money_valuation: float | None = None
    post_money_valuation: float | None = None
    total_funding_after_round: float | None = None
    claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    last_verified_at: datetime | None = None


class ClaimTrace(VencertiaBaseModel):
    claim_id: str
    status: str = "UNKNOWN"  # SUPPORTED/PARTIAL/CONFLICTED/REJECTED/STALE/UNKNOWN
    evidence_trace: list[dict] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
