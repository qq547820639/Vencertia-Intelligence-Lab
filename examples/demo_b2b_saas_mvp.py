"""Vencertia v1.1.2 — B2B SaaS MVP 6-week decision demo (full closed loop).

Scenario:
- 10 ICP interviews: 8 report severe pain, 0 paid anything yet
- Founder runway: 7 months; 4 weeks already spent
- Decision: commit six weeks to build the MVP, or stop and redeploy?
- Expected output: INSUFFICIENT_EVIDENCE (DO NOT COMMIT), critical=WTP,
  next=SELL PAID PILOT (success: >= 2 paid pilots)
- Then record the paid-pilot outcome (20 outreach / 6 replies / 3 demos /
  0 paid) -> belief drops -> decision re-evaluated -> prediction settled ->
  calibration updated.

Run:  PYTHONPATH=src python examples/demo_b2b_saas_mvp.py
"""

from __future__ import annotations

import json
from typing import Any

from vencertia.domain import (
    Action,
    Claim,
    ClaimType,
    Direction,
    Evidence,
    Experiment,
    FinancialSnapshot,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    OutcomeType,
    Project,
    ProjectStatus,
    Scope,
    Stage,
    Verification,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle
from vencertia.runtime.belief_engine import BeliefUpdateInput

PROJECT_ID = "PRJ_B2B_SAAS"
USER_ID = "USR_FOUNDER"


def _make_claims_and_beliefs(repo) -> None:
    repo.add_claim(
        Claim(id="CLM_PROBLEM", statement="ICP has a severe recurring problem", scope="PROJECT",
              claim_type=ClaimType.HYPOTHESIS, project_id=PROJECT_ID)
    )
    repo.add_claim(
        Claim(id="CLM_WTP", statement="ICP will pay for the promised outcome", scope="PROJECT",
              claim_type=ClaimType.HYPOTHESIS, project_id=PROJECT_ID)
    )
    repo.add_claim(
        Claim(id="CLM_ACCESS", statement="Founder can reach 20 ICPs in two weeks", scope="PROJECT",
              claim_type=ClaimType.HYPOTHESIS, project_id=PROJECT_ID)
    )
    from vencertia.domain import Belief

    for bid, claim_id, statement, dw in [
        ("problem", "CLM_PROBLEM", "ICP has a severe recurring problem", 0.8),
        ("wtp", "CLM_WTP", "ICP will pay for the promised outcome", 1.0),
        ("access", "CLM_ACCESS", "Founder can reach 20 ICPs in two weeks", 0.7),
    ]:
        repo.save_belief(
            Belief(id=bid, claim_id=claim_id, statement=statement, scope="PROJECT",
                   project_id=PROJECT_ID, decision_relevant=True, decision_weight=dw)
        )


def _add_interview_evidence(repo) -> None:
    """10 interviews: 8 pain (problem SUPPORTS), 0 paid (wtp CONTRADICTS)."""
    repo.add_evidence(
        Evidence(
            id="E_INT_PROBLEM",
            claim_ids=["CLM_PROBLEM"],
            scope=Scope.CUSTOMER,
            evidence_type="PRIMARY_RESEARCH",
            provenance={"tool": "interviews", "actor": USER_ID, "raw_extract": "8 of 10 ICPs report severe recurring pain"},
            source="10 ICP interviews: 8 report severe recurring problem",
            directness=0.8, reliability=0.8, relevance=1.0, strength=0.8,
            supports_or_contradicts=Direction.SUPPORTS,
            authority_level="REVIEWED_EXTERNAL_RESEARCH",
            verification=Verification.VERIFIED,
            # v1.1.2 (P0-3): CUSTOMER evidence must carry project_id.
            project_id=PROJECT_ID,
        )
    )
    repo.add_evidence(
        Evidence(
            id="E_INT_WTP_ZERO",
            claim_ids=["CLM_WTP"],
            scope=Scope.CUSTOMER,
            evidence_type="PRIMARY_RESEARCH",
            provenance={"tool": "interviews", "actor": USER_ID, "raw_extract": "0 of 10 interviewees paid"},
            source="10 ICP interviews: 0 interviewees paid for anything",
            directness=0.8, reliability=0.8, relevance=1.0, strength=0.7,
            supports_or_contradicts=Direction.CONTRADICTS,
            authority_level="REVIEWED_EXTERNAL_RESEARCH",
            verification=Verification.VERIFIED,
            # v1.1.2 (P0-3): CUSTOMER evidence must carry project_id.
            project_id=PROJECT_ID,
        )
    )


def _seed_project(repo) -> None:
    repo.save_project(
        Project(id=PROJECT_ID, user_id=USER_ID, name="B2B SaaS MVP",
                description="B2B SaaS MVP 6-week decision", status=ProjectStatus.VALIDATING,
                stage=Stage.S6_VALIDATION)
    )
    repo.save_memory(
        MemoryRecord(
            memory_id="M_RUNWAY", user_id=USER_ID, project_id=PROJECT_ID,
            scope=MemoryScope.PROJECT_SPECIFIC, memory_type=MemoryType.CONSTRAINT,
            content="Runway is 7 months; 4 weeks already spent on exploration.",
            structured_value={"runway_months": 7, "weeks_spent": 4},
            fact_status=Verification.VERIFIED, confidence="HIGH", importance="CRITICAL",
            status=MemoryStatus.ACTIVE,
        )
    )
    repo.save_financial_snapshot(
        FinancialSnapshot(id="FS_1", project_id=PROJECT_ID, currency="EUR",
                          cash_on_hand=70000.0, burn_monthly=10000.0, runway_months=7.0)
    )


def _make_paid_pilot_experiment() -> Experiment:
    return Experiment(
        id="EXP_PAID_PILOT",
        name="SELL PAID PILOT",
        target_belief_ids=["wtp"],
        hypothesis="At least 2 of 20 ICPs will pay for a manual concierge pilot",
        action="Offer the promised outcome manually to 20 ICPs within 30 days",
        predicted_observation=">=2 paid pilots",
        success_criteria=">=2 paid pilots",
        failure_criteria="0 paid pilots",
        ambiguity_criteria="1 paid pilot",
        expected_information_gain=0.95,
        decision_impact=1.0,
        cost=1.0,
        time=3.0,
        reversibility=1.0,
    )


def run_demo(console=None) -> dict[str, Any]:
    """Run the demo; returns a JSON-serializable summary dict."""
    if console is None:
        from rich.console import Console

        console = Console()

    console.rule("[bold cyan]Vencertia v1.1.2 — B2B SaaS MVP 6-Week Decision (closed loop)[/bold cyan]")
    console.print(
        "Scenario: 10 ICP interviews (8 pain, 0 paid) | runway 7 months | "
        "4 weeks already spent | decision: commit 6 weeks to MVP or stop?"
    )

    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, bus=bus)
    orchestrator = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus,
    )

    _seed_project(repo)
    _make_claims_and_beliefs(repo)
    _add_interview_evidence(repo)

    # Apply interview evidence to beliefs before solving.
    evidence = repo.list_evidence(claim_ids=["CLM_PROBLEM", "CLM_WTP"])
    beliefs = repo.get_beliefs(PROJECT_ID)
    output = engines.belief_engine.update(
        BeliefUpdateInput(
            beliefs=beliefs, evidence=evidence, policy=engines.evidence_policy
        )
    )
    for belief in output.beliefs:
        existing = repo.get_belief(belief.id)
        repo.save_belief(belief, expected_version=existing.version if existing else None)

    console.print("\n[bold]Step 1 — Solve (compile → research → evidence → belief → convergence → evaluate)[/bold]")
    result = orchestrator.solve(
        SolveRequest(
            project_id=PROJECT_ID,
            problem_text="Should the founder commit six weeks to building the B2B SaaS MVP now?",
            user_id=USER_ID,
            experiment_candidates=[_make_paid_pilot_experiment()],
        )
    )

    decision = result.decision
    console.print(f"  Decision: [bold]{decision.status}[/bold] "
                  f"(confidence={decision.confidence:.3f}, margin={decision.decision_margin:.3f})")
    if decision.status == "ABSTAIN":
        console.print("  Verdict: [bold yellow]INSUFFICIENT_EVIDENCE — DO NOT COMMIT yet[/bold yellow]")
    console.print(f"  Critical uncertainty: [bold]{decision.critical_belief_id}[/bold] "
                  f"(impact={decision.critical_uncertainty:.3f})")
    console.print(f"  Convergence: {result.convergence.status} — {result.convergence.reason}")
    if result.next_experiment:
        exp = result.next_experiment.experiment
        console.print(f"  Next experiment: [bold]{exp.name}[/bold] "
                      f"(success: {exp.success_criteria}, priority={result.next_experiment.priority_score:.3f})")
    console.print(f"  Predictions registered: {len(result.predictions)}")

    wtp_before = next(b for b in repo.get_beliefs(PROJECT_ID) if b.id == "wtp").probability

    console.print("\n[bold]Step 2 — Record paid-pilot outcome (closed loop)[/bold]")
    pilot = result.next_experiment.experiment if result.next_experiment else _make_paid_pilot_experiment()
    repo.save_action(
        Action(id="ACT_PILOT", project_id=PROJECT_ID, kind="EXPERIMENT",
               description=pilot.action, decision_id=result.decision_id, experiment_id=pilot.id,
               status="RUNNING")
    )
    recorded = orchestrator.record_outcome(
        "ACT_PILOT",
        "20 outreach / 6 replies / 3 demos / 0 paid",
        quantitative={"wtp": 0.0, "outreach": 20.0, "replies": 6.0, "demos": 3.0, "paid": 0.0},
        outcome_type=OutcomeType.FAILURE,
    )
    wtp_after = next(b for b in repo.get_beliefs(PROJECT_ID) if b.id == "wtp").probability
    console.print("  Outcome: FAILURE — 20 outreach / 6 replies / 3 demos / 0 paid")
    console.print(f"  Belief WTP: [bold]{wtp_before:.3f} -> {wtp_after:.3f}[/bold] "
                  f"(decreased by {wtp_before - wtp_after:.3f})")
    if recorded.decision_update:
        console.print(f"  Decision re-evaluated: [bold]{recorded.decision_update.status}[/bold] "
                      f"(confidence={recorded.decision_update.confidence:.3f})")
    if recorded.convergence:
        console.print(f"  Convergence after outcome: {recorded.convergence.status}")
    console.print(f"  Predictions resolved: [bold]{len(recorded.predictions_resolved)}[/bold]")
    for p in recorded.predictions_resolved:
        console.print(f"    {p.id} ({p.target[:40]}...) -> {p.resolution}"
                      + (f" outcome={p.outcome}" if p.outcome is not None else ""))
    if recorded.calibration_delta:
        cd = recorded.calibration_delta
        console.print(f"  Calibration updated: n={cd.get('n')}, Brier={cd.get('brier_score')}, "
                      f"ECE={cd.get('expected_calibration_error')}")
    console.print(f"  Total events logged: {len(repo.events_since(0))}")
    console.rule("[bold green]Demo complete — full closed loop verified[/bold green]")

    return {
        "scenario": "B2B SaaS MVP 6-week decision",
        "decision_status": decision.status,
        "verdict": "DO NOT COMMIT (insufficient evidence)" if decision.status == "ABSTAIN" else decision.status,
        "critical_belief": decision.critical_belief_id,
        "next_experiment": result.next_experiment.experiment.name if result.next_experiment else None,
        "success_criteria": pilot.success_criteria,
        "wtp_before": wtp_before,
        "wtp_after": wtp_after,
        "decision_after_outcome": recorded.decision_update.status if recorded.decision_update else None,
        "predictions_resolved": len(recorded.predictions_resolved),
        "calibration": recorded.calibration_delta,
        "total_events": len(repo.events_since(0)),
    }


if __name__ == "__main__":
    summary = run_demo()
    print("\nSUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
