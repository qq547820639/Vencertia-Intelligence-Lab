"""Quick-solve — one-shot end-to-end decision on an in-memory store.

Runs the full loop (compile → research → solve → summary) with the CONFIGURED
providers (v2.0.1: no hardcoded mock — the product uses the real AI path from
Settings; tests opt into mock explicitly via ``VENCERTIA_MODEL_PROVIDER=mock``).
Nothing is written to a persistent Decision Ledger, so the result is marked
``lightweight=True``.
"""

from __future__ import annotations

from vencertia.config import get_settings
from vencertia.domain import DecisionOption, SolveMode
from vencertia.events.bus import EventBus
from vencertia.presentation import solve_summary
from vencertia.providers.factory import create_provider_bundle
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle

QUICK_PROBLEM = "Should we commit six weeks to building the MVP now?"
QUICK_OPTIONS = [
    {"id": "commit", "label": "Commit six weeks to MVP"},
    {"id": "stop", "label": "Stop and redeploy"},
]


def run_quick_solve(
    problem_text: str | None = None,
    options: list[dict] | None = None,
) -> dict:
    """Run a one-shot solve on an in-memory store; return the summary dict.

    ``problem_text``/``options`` override the built-in scenario when given.
    Providers come from the configured Settings (real AI path by default).
    """
    settings = get_settings()
    providers = create_provider_bundle(settings)
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    orchestrator = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        bus=bus,
        model=providers.model,
        search=providers.search,
        retrieval=providers.retrieval,
        settings=settings,
    )
    request = SolveRequest(
        project_id="PRJ_QUICK",
        problem_text=problem_text or QUICK_PROBLEM,
        options=[DecisionOption(**o) for o in options] if options else None,
        mode=SolveMode.OPERATE,
    )
    result = orchestrator.solve(request)
    summary = solve_summary(result)
    # 轻量模式：InMemory 一次性，未写完整 Decision Ledger。
    summary["lightweight"] = True
    return summary
