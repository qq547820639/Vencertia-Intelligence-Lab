"""ApplicationContainer — the single composition root (ADR-009).

Assembly chain: Settings → Repository Factory → Provider Factory → EngineBundle
→ SolveOrchestrator → FastAPI / typer. ``api.py`` and ``cli.py`` share this
root; swapping providers only touches ``providers/factory.py``.
"""

from __future__ import annotations

from vencertia.config import Settings, get_settings
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.providers.factory import (
    ProviderBundle,
    create_provider_bundle,
    provider_name,
)
from vencertia.repositories.base import Repository
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import (
    EngineBundle,
    SolveOrchestrator,
    default_engine_bundle,
)


class ApplicationContainer:
    """Single wiring root for the whole application."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._repo: Repository | None = None
        self._bus: EventBus | None = None
        self._providers: ProviderBundle | None = None
        self._engines: EngineBundle | None = None
        self._orchestrator: SolveOrchestrator | None = None
        self._call_recorder = None
        self._skills = None
        self._skill_router = None

    # -- assembly ---------------------------------------------------------------

    def _build_repository(self) -> Repository:
        if self._settings.postgres_dsn:
            from vencertia.repositories.postgres import PostgresRepository

            # DSN-gated (ADR-005): misconfiguration (missing driver) fails loud —
            # PostgresDisabledError propagates, no silent fallback to SQLite.
            return PostgresRepository(self._settings.postgres_dsn)
        if self._settings.db_dsn == "sqlite:///:memory:" or self._settings.db_dsn == ":memory:":
            return InMemoryRepository()
        return SQLiteRepository(self._settings.db_dsn)

    # -- properties --------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def repository(self) -> Repository:
        if self._repo is None:
            self._repo = self._build_repository()
        return self._repo

    @property
    def bus(self) -> EventBus:
        if self._bus is None:
            self._bus = EventBus(sink=self.repository.append_event)
        return self._bus

    @property
    def call_recorder(self):
        """Shared CallRecorder for provider observability (P1-7).

        Cached: every consumer of this property must observe the SAME recorder
        instance (previous behavior created a new instance per access).
        """
        if self._call_recorder is None:
            from vencertia.runtime.observability import CallRecorder

            self._call_recorder = CallRecorder(
                self.repository,
                enabled=self.settings.call_log_enabled,
                settings=self.settings,
            )
        return self._call_recorder

    @property
    def providers(self) -> ProviderBundle:
        if self._providers is None:
            self._providers = create_provider_bundle(
                self._settings, recorder=self.call_recorder
            )
            self.bus.publish(
                make_event(
                    EventType.PROVIDER_SELECTED,
                    "provider",
                    self._settings.model_provider,
                    {
                        "model": provider_name(self._providers.model),
                        "search": (
                            provider_name(self._providers.search)
                            if self._providers.search is not None
                            else None
                        ),
                        "retrieval": (
                            provider_name(self._providers.retrieval)
                            if self._providers.retrieval is not None
                            else None
                        ),
                    },
                )
            )
        return self._providers

    @property
    def engines(self) -> EngineBundle:
        if self._engines is None:
            self._engines = default_engine_bundle(
                self.repository, self.settings, self.bus
            )
        return self._engines

    @property
    def orchestrator(self) -> SolveOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = SolveOrchestrator(
                repo=self.repository,
                policy=self.engines.evidence_policy,
                engines=self.engines,
                model=self.providers.model,
                search=self.providers.search,
                retrieval=self.providers.retrieval,
                bus=self.bus,
                settings=self.settings,
            )
        return self._orchestrator

    # -- v2.0 skill layer --------------------------------------------------------

    @property
    def skills(self):
        """V11 迁移 skill 目录（经验资产，版本化）。"""
        if self._skills is None:
            from vencertia.skills import build_biz_skill_registry

            self._skills = build_biz_skill_registry(model=self.providers.model)
        return self._skills

    @property
    def skill_router(self):
        """编排路由：按阶段运行 skill + 契约/引用校验门。"""
        if self._skill_router is None:
            from vencertia.skills import SkillRouter

            self._skill_router = SkillRouter(self.skills)
        return self._skill_router

    # -- applications -------------------------------------------------------------

    def fastapi_app(self):
        from vencertia.api import create_app

        return create_app(self.settings, self.repository, self.orchestrator)

    def typer_app(self):
        from vencertia.cli import app

        return app


def build_container(settings: Settings | None = None) -> ApplicationContainer:
    """Build (and cache) the application container for the given settings."""
    return ApplicationContainer(settings)
