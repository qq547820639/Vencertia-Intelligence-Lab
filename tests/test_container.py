"""ApplicationContainer tests (ADR-009): single composition root."""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.container import build_container
from vencertia.providers.factory import (
    ProviderError,
    with_resilience,
)
from vencertia.providers.mock import MockProvider
from vencertia.runtime import SolveOrchestrator


def test_container_builds_mock_bundle():
    container = build_container(Settings(model_provider="mock", search_provider="mock", db_dsn="sqlite:///:memory:"))
    assert container.settings.model_provider == "mock"
    assert container.repository is not None
    assert container.bus is not None
    assert container.providers.model is not None
    assert container.engines is not None
    assert container.orchestrator is not None


def test_container_wires_same_repository():
    container = build_container(Settings(model_provider="mock", search_provider="mock", db_dsn="sqlite:///:memory:"))
    assert container.repository is container.repository  # cached
    assert container.orchestrator.repo is container.repository


def test_container_typer_and_fastapi():
    container = build_container(Settings(model_provider="mock", search_provider="mock", db_dsn="sqlite:///:memory:"))
    app = container.fastapi_app()
    assert app.title == "Vencertia Decision Runtime"
    typer_app = container.typer_app()
    assert typer_app.info.help is not None


def test_container_openai_compatible_builds_without_key():
    """openai_compatible builds even without credentials; calls fail structured."""
    settings = Settings(model_provider="openai_compatible", search_provider="mock", openai_api_key=None)
    container = build_container(settings)
    assert container.providers.model is not None
    assert container.orchestrator is not None


def test_provider_factory_unknown_provider_raises():
    from vencertia.providers.factory import create_model_provider

    with pytest.raises(ProviderError):
        create_model_provider(Settings(model_provider="does_not_exist"))


class FlakyProvider(MockProvider):
    """Fails N times then succeeds (used with retries disabled)."""

    def __init__(self, failures: int = 1) -> None:
        super().__init__()
        self.failures = failures
        self.calls = 0

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("timeout")
        return super().generate_structured(task, schema, context)


def test_with_resilience_retries_then_succeeds():
    settings = Settings(provider_max_retries=2, provider_retry_backoff_base=0.0)
    inner = FlakyProvider(failures=1)
    wrapped = with_resilience(inner, settings)
    result = wrapped.generate_structured("t", {"kind": "compile"}, {})
    assert inner.calls == 2  # 1 failure + 1 retry
    assert "objective" in result


def test_with_resilience_returns_structured_error():
    settings = Settings(provider_max_retries=0, provider_retry_backoff_base=0.0)
    inner = FlakyProvider(failures=5)
    wrapped = with_resilience(inner, settings)
    with pytest.raises(ProviderError):
        wrapped.generate_structured("t", {"kind": "compile"}, {})


def test_default_runtime_uses_container_providers():
    settings = Settings(model_provider="mock", search_provider="mock", db_dsn="sqlite:///:memory:")
    container = build_container(settings)
    runtime = container.orchestrator
    assert isinstance(runtime, SolveOrchestrator)
    assert runtime.model is container.providers.model
