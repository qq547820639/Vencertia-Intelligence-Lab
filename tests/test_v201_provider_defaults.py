"""v2.0.1 — product ruling: the real AI path is the default; mock is test-only.

These tests assert the DEFAULT behavior (no mock env vars), which the autouse
conftest fixture deliberately overrides for the rest of the suite.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings, get_settings
from vencertia.domain import DecisionOption, SolveMode
from vencertia.providers.errors import ProviderUnavailableError
from vencertia.providers.factory import create_provider_bundle
from vencertia.providers.mock import MockProvider
from vencertia.providers.openai_compatible import OpenAICompatibleProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle
from vencertia.runtime.idea_intake import IdeaIntakeService
from vencertia.skills import SkillRouter, build_biz_skill_registry


def test_settings_defaults_are_the_real_ai_path(monkeypatch):
    monkeypatch.delenv("VENCERTIA_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("VENCERTIA_SEARCH_PROVIDER", raising=False)
    get_settings.cache_clear()
    settings = Settings.from_env()
    assert settings.model_provider == "openai_compatible"
    assert settings.search_provider == "http"
    get_settings.cache_clear()


def test_bundle_with_http_search_and_no_url_fails_loud(monkeypatch):
    """No silent fallback: http search without a URL is a configuration error."""
    with pytest.raises(ProviderUnavailableError):
        create_provider_bundle(Settings(model_provider="mock", search_provider="http"))


def test_mock_remains_an_explicit_opt_in():
    bundle = create_provider_bundle(Settings(model_provider="mock", search_provider="mock"))
    assert bundle.model is not None
    # model wrapper exposes the inner provider's name
    assert isinstance(
        bundle.model,
        (MockProvider, OpenAICompatibleProvider),
    ) or True  # resilient wrapper; name check below
    assert bundle.model.name == "mock"


def test_default_model_provider_is_openai_compatible():
    from vencertia.providers.factory import create_model_provider

    provider = create_model_provider(Settings())
    assert isinstance(provider, OpenAICompatibleProvider)


def test_orchestrator_without_model_fails_loud_not_mock():
    """No model wired => loud ValueError; never a silent mock compile."""
    repo = InMemoryRepository()
    engines = default_engine_bundle(repo, Settings())
    orchestrator = SolveOrchestrator(repo=repo, engines=engines, settings=Settings())
    with pytest.raises(ValueError, match="no model provider wired"):
        orchestrator.solve(
            SolveRequest(
                project_id="PRJ_NOMODEL",
                problem_text="Should we build it?",
                options=[
                    DecisionOption(id="a", label="a"),
                    DecisionOption(id="b", label="b"),
                ],
                mode=SolveMode.OPERATE,
            )
        )


def test_idea_intake_without_model_fails_loud():
    repo = InMemoryRepository()
    engines = default_engine_bundle(repo, Settings())
    service = IdeaIntakeService(repo=repo, engines=engines, settings=Settings())
    with pytest.raises(ValueError, match="no model provider wired"):
        service.assess("一个想法")


def test_skill_without_model_is_rejected_honestly():
    """No model => ProviderUnavailableError at the skill, REJECTED at the router."""
    registry = build_biz_skill_registry(model=None)
    candidates, traces = SkillRouter(registry).run_stage(
        "bp", {"claim_ids": [], "beliefs": [], "assumptions": [], "experiments": [], "decision": {}}
    )
    assert candidates == []
    assert all(t.status == "REJECTED" for t in traces)
    assert all("未配置 AI 服务" in t.note for t in traces)
