"""Provider observability records (v1.1).

The red line (ADR-012): :class:`ProviderCallRecord` must NEVER contain prompt
text or other sensitive content — only call metadata and outcome.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class ProviderCallRecord(VencertiaBaseModel):
    """Metadata of one external provider call (model/search/retrieval/research)."""

    id: str  # PCR_...
    kind: str = "model"  # model | search | retrieval | research
    provider: str = ""
    model: str = ""
    request_id: str = ""
    task_kind: str = ""  # compile | research_plan | extract | match | research_run | ...
    started_at: datetime = Field(default_factory=utcnow)
    latency_ms: float = 0.0
    tokens: dict = Field(default_factory=dict)  # {input, output}
    cost: float = 0.0
    success: bool = True
    retry_count: int = 0
    error_type: str | None = None
    version: int = 1
