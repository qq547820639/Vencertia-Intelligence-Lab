"""IdeaIntakeService — 入口层：想法 → 结构化决策问题 + 假设清单（v2.0）。

A read-only assessment pipeline over EXISTING engines: the raw idea is
compiled by the DecisionCompiler (mock deterministic offline, or a real LLM
when configured), then the uncertainty engine ranks the compiled beliefs into
an assumption register with biggest unknowns. No state is persisted by
``assess()`` — the returned ``solve_request`` is ready for ``POST /v1/solve``
when the owner decides to run the full judgment loop.

Honesty contract (same as the rest of the runtime): the assumption register is
a MODEL PROPOSAL (LLM_PROPOSED provenance), never silently treated as truth —
the solve loop re-validates everything deterministically.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import Field

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    DecisionOption,
    SolveMode,
    VencertiaBaseModel,
    utcnow,
)
from vencertia.providers.mock import MockProvider
from vencertia.repositories.base import Repository

IDEA_DISCLAIMER = (
    "离线确定性评估：假设清单与决策问题由模型提议（LLM_PROPOSED），未经你确认；"
    "关键未知按确定性引擎排序。进入决策后所有假设会被重新校验。"
)


class IdeaAssessment(VencertiaBaseModel):
    """Structured assessment of a raw idea (v2.0 intake projection)."""

    idea_id: str
    idea_text: str
    decision_question: str
    options: list[DecisionOption] = Field(default_factory=list)
    # assumption register: compiled beliefs with their priors
    assumptions: list[dict] = Field(default_factory=list)
    # top critical unknowns (uncertainty engine ranking)
    biggest_unknowns: list[dict] = Field(default_factory=list)
    recommended_mode: str = "EXPLORE"  # idea-stage default (V-7 vocabulary)
    solve_request: dict = Field(default_factory=dict)
    disclaimer: str = IDEA_DISCLAIMER
    assessed_at: str = Field(default_factory=lambda: utcnow().isoformat())


class IdeaIntakeService:
    """Compiles a raw idea into a decision structure + assumption register."""

    def __init__(
        self,
        repo: Repository,
        engines,
        settings: Settings | None = None,
        compiler=None,
        model=None,
    ) -> None:
        self.repo = repo
        self.engines = engines
        self.settings = settings or get_settings()
        self.compiler = compiler
        self.model = model

    def assess(
        self,
        idea_text: str,
        domain: str = "general",
        user_id: str | None = None,
        options: list[DecisionOption] | None = None,
    ) -> IdeaAssessment:
        """Compile the idea and rank its assumptions — no persistence."""
        project_id = "PRJ_IDEA_" + uuid4().hex[:12]
        compiler = self.compiler
        if compiler is None:
            from vencertia.capabilities import DecisionCompiler

            compiler = DecisionCompiler(
                model=self.model or MockProvider(),
                settings=self.settings,
                repo=self.repo,
            )
        compiled = compiler.compile(
            idea_text,
            {
                "project_id": project_id,
                "user_id": user_id or "u_default",
                "domain": domain,
                "model_tag": "mock",
            },
            options=options,
        )

        decision = compiled.decision
        beliefs = compiled.beliefs
        assumptions: list[dict] = []
        for belief in sorted(beliefs, key=lambda b: b.uncertainty, reverse=True):
            assumptions.append(
                {
                    "belief_id": belief.id,
                    "claim_id": belief.claim_id,
                    "statement": belief.statement,
                    "scope": _enum(belief.scope),
                    "prior_probability": round(float(belief.prior), 4),
                    "uncertainty": round(float(belief.uncertainty), 4),
                    "proposed_by_model": True,  # LLM_PROPOSED until validated
                }
            )

        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)
        biggest_unknowns = [
            {
                "belief_id": c.belief_id,
                "statement": c.statement,
                "uncertainty": round(float(c.uncertainty), 4),
                "impact": round(float(c.impact), 4),
            }
            for c in criticals[:3]
        ]

        solve_request = {
            "project_id": project_id,
            "problem_text": decision.decision_question or idea_text,
            "mode": SolveMode.EXPLORE.value,
            "domain": domain,
            "options": [o.model_dump(mode="json") for o in decision.options],
        }

        return IdeaAssessment(
            idea_id="IDEA_" + uuid4().hex[:10],
            idea_text=idea_text,
            decision_question=decision.decision_question or idea_text,
            options=decision.options,
            assumptions=assumptions,
            biggest_unknowns=biggest_unknowns,
            solve_request=solve_request,
        )


def _enum(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
