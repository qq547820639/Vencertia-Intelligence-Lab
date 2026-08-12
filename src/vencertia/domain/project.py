"""Project: lifecycle status/stage plus financial snapshots."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class ProjectStatus(str, Enum):
    IDEA = "IDEA"
    EXPLORING = "EXPLORING"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    PIVOTING = "PIVOTING"
    HOLD = "HOLD"
    KILLED = "KILLED"
    ARCHIVED = "ARCHIVED"


class Stage(str, Enum):
    S0_INITIALIZATION = "S0_INITIALIZATION"
    S1_FOUNDER_DIAGNOSIS = "S1_FOUNDER_DIAGNOSIS"
    S2_OPPORTUNITY_DISCOVERY = "S2_OPPORTUNITY_DISCOVERY"
    S3_VENTURE_DESIGN = "S3_VENTURE_DESIGN"
    S4_PROJECT_CHALLENGE = "S4_PROJECT_CHALLENGE"
    S5_PROJECT_CONVERGENCE = "S5_PROJECT_CONVERGENCE"
    S6_VALIDATION = "S6_VALIDATION"
    S7_BUSINESS_MODEL = "S7_BUSINESS_MODEL"
    S8_EXECUTION = "S8_EXECUTION"
    S9_SCALE_OR_DECISION = "S9_SCALE_OR_DECISION"


class Project(VencertiaBaseModel):
    id: str  # PRJ_...
    user_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.IDEA
    stage: Stage = Stage.S0_INITIALIZATION
    is_primary: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class ProjectKB(VencertiaBaseModel):
    project_id: str
    entries: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utcnow)


class FinancialSnapshot(VencertiaBaseModel):
    id: str  # FS_...
    project_id: str
    as_of: datetime = Field(default_factory=utcnow)
    currency: str = "EUR"
    cash_on_hand: float | None = None
    burn_monthly: float | None = None
    runway_months: float | None = None
    revenue_monthly: float | None = None
    gross_margin: float | None = None
    unit_economics: dict = Field(default_factory=dict)
    source_evidence_ids: list[str] = Field(default_factory=list)
    version: int = 1
