"""Objective: first-class citizen that decisions optimize."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import Scope, VencertiaBaseModel, utcnow


class ObjectiveDirection(str, Enum):
    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


class Objective(VencertiaBaseModel):
    id: str
    owner: str  # user_id
    scope: Scope = Scope.PROJECT
    name: str
    description: str = ""
    metric: str = "expected company value (incl. option value)"
    direction: ObjectiveDirection = ObjectiveDirection.MAXIMIZE
    weight: float = 1.0
    constraints: list[str] = Field(default_factory=list)
    time_horizon: str = "18 months"
    priority: int = Field(default=5, ge=0, le=10)
    source: str = "user"  # user | system | capability
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1
