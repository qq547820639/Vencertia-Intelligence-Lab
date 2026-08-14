"""CompilationService — decision compilation + persistence (P2-16).

Extracted from SolveOrchestrator so the facade delegates compilation, compiled
state persistence and context building to a dedicated service. Behavior is
identical to the v1.1.1 inline logic (SolveResult schema unchanged).
"""

from __future__ import annotations

from typing import Any

from vencertia.config import Settings, get_settings
from vencertia.domain import Project
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.providers.models import ModelProvider
from vencertia.repositories.base import Repository


class CompilationService:
    """Compile a problem statement into candidate state and persist it."""

    def __init__(
        self,
        repo: Repository,
        engines,
        settings: Settings | None = None,
        bus: EventBus | None = None,
        model: ModelProvider | None = None,
        compiler: Any | None = None,
    ) -> None:
        self.repo = repo
        self.engines = engines
        self.settings = settings or get_settings()
        self.bus = bus
        self.model = model
        self.compiler = compiler

    def compile(
        self,
        request: Any,
        project: Project,
        context: Any | None,
    ):
        """Compile candidate Objective/Decision/Claims/Beliefs/Experiments."""
        compiler = self.compiler
        if compiler is None:
            from vencertia.capabilities import DecisionCompiler as DC

            if self.model is None:
                # v2.0.1 (product ruling): NO silent mock fallback.
                raise ValueError(
                    "no model provider wired: configure VENCERTIA_MODEL_PROVIDER "
                    "(mock is a test/development-only explicit opt-in)"
                )
            compiler = DC(model=self.model, settings=self.settings, repo=self.repo)
            self.compiler = compiler
        return compiler.compile(
            request.problem_text,
            {
                "project_id": project.id,
                "user_id": project.user_id,
                "domain": request.domain,
                "model_tag": request.model_tag,
            },
            options=request.options,
            context=context,
        )

    def persist(self, compiled, request: Any) -> None:
        """Persist compiled objective/claims/beliefs (existing canonical wins)."""
        if self.repo.get_objective(compiled.objective.id) is None:
            self.repo.save_objective(compiled.objective)
        for claim in compiled.claims:
            if self.repo.get_claim(claim.id) is None:
                self.repo.add_claim(claim)
        existing = self.repo.get_beliefs(request.project_id)
        existing_by_claim = {b.claim_id: b for b in existing}
        for belief in compiled.beliefs:
            if belief.claim_id in existing_by_claim:
                continue
            belief.project_id = request.project_id
            self.repo.save_belief(belief)
        if self.bus is not None:
            self.bus.publish(
                make_event(EventType.DECISION_CREATED, "decision", compiled.decision.id, {})
            )
            # v1.9: canonical context inputs changed (new claims/beliefs) — any
            # consumer caching a project's context projection must rebuild.
            self.bus.publish(
                make_event(
                    EventType.CONTEXT_INVALIDATED,
                    "project",
                    request.project_id,
                    {"decision_id": compiled.decision.id},
                )
            )

    def build_context(
        self,
        project: Project,
        request: Any,
        decision: Any | None = None,
    ):
        """Build the context projection (P0-1: decision-aware post-compile)."""
        if self.engines.context_builder_v11 is not None:
            return self.engines.context_builder_v11.build_for_decision(
                project.id, user_id=request.user_id, limit=15, decision=decision
            )
        return self.engines.context_builder.build(project.id, request.user_id, limit=15)
