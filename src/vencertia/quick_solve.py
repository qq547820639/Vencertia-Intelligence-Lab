"""Quick-solve — one-shot end-to-end decision with an in-memory store.

A single command runs the full loop (compile → research → solve → summary) on an
:class:`~vencertia.repositories.memory.InMemoryRepository` with mock providers.
Nothing is written to a persistent Decision Ledger, so the result is marked
``lightweight=True`` (a "轻量模式" demo of the 5-section contract).
"""

from __future__ import annotations

from vencertia.domain import DecisionOption, SolveMode
from vencertia.events.bus import EventBus
from vencertia.presentation import solve_summary
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
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

    ``problem_text``/``options`` override the built-in demo scenario; when
    omitted, the deterministic ``QUICK_PROBLEM`` / ``QUICK_OPTIONS`` constants
    are used so the command is reproducible offline.
    """
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, bus=bus)
    orchestrator = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
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
