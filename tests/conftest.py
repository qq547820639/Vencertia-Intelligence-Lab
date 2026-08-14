"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings, get_settings
from vencertia.domain import Belief
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle
from vencertia.runtime.evidence_policy import EvidencePolicy


@pytest.fixture(autouse=True)
def _mock_provider_env(monkeypatch):
    """v2.0.1: tests opt into the mock provider EXPLICITLY.

    The product default is the real AI path (openai_compatible / http search);
    the test suite runs in an explicitly-mock environment so it never depends
    on ambient credentials. Tests asserting the product defaults must delenv
    these variables themselves (see tests/test_v201_provider_defaults.py).
    """
    monkeypatch.setenv("VENCERTIA_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("VENCERTIA_SEARCH_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


# Five-section solve_summary contract keys (shared across v1.3/v1.4 tests).
FIVE_KEYS = {"current_judgment", "rationale", "biggest_unknown", "next_step", "change_condition"}


@pytest.fixture
def orchestrator() -> SolveOrchestrator:
    """A bare SolveOrchestrator wired to mock providers (no persistent store)."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    return SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )


@pytest.fixture
def api_client() -> TestClient:
    """A TestClient over a fully-wired in-memory app (API-layer contract tests)."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        bus=bus,
        settings=settings,
    )
    return TestClient(create_app(settings, repo, runtime))
