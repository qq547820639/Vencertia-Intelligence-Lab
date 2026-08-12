"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from vencertia.config import Settings, get_settings
from vencertia.domain import Belief
from vencertia.events.bus import EventBus
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.evidence_policy import EvidencePolicy


def make_belief(bid: str, p: float, alpha: float, beta: float, weight: float = 1.0,
                scope: str = "PROJECT") -> Belief:
    """Build a belief with derived uncertainty (same formula as BeliefEngine)."""
    variance = 4.0 * p * (1.0 - p)
    mass = alpha + beta - 2.0
    maturity = 1.0 / (1.0 + mass / 6.0)
    unc = max(0.0, min(1.0, variance * (0.35 + 0.65 * maturity)))
    return Belief(
        id=bid,
        claim_id="CLM_" + bid,
        statement=bid,
        scope=scope,
        project_id="PRJ_1",
        posterior=p,
        probability=p,
        alpha=alpha,
        beta=beta,
        uncertainty=unc,
        confidence=1.0 - unc,
        decision_weight=weight,
        decision_relevant=True,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def policy(settings) -> EvidencePolicy:
    return EvidencePolicy(settings)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
