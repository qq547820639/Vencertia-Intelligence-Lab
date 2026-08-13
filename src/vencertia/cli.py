"""Vencertia v1.1 CLI (typer + rich, fully parameterized, non-interactive).

All commands build through :class:`~vencertia.container.ApplicationContainer`
(ADR-009); there is no second wiring path.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vencertia.config import Settings, get_settings
from vencertia.domain import Decision, Evidence, OutcomeType
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.runtime import SolveOrchestrator, SolveRequest

app = typer.Typer(help="Vencertia Adaptive Decision System v1.1")
console = Console()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(data, label: str = "result") -> None:
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def _settings_with_db(db: str | None) -> Settings:
    settings = get_settings()
    if db:
        d = settings.__dict__.copy()
        d["db_dsn"] = f"sqlite:///{db}"
        return Settings(**d)
    return settings


def _default_runtime(settings: Settings) -> tuple[SolveOrchestrator, Repository]:
    from vencertia.container import build_container

    container = build_container(settings)
    return container.orchestrator, container.repository


# ---------------------------------------------------------------------------


@app.command()
def solve(request_path: Path, db: str | None = None, advanced: bool = False) -> None:
    """Run the full solve loop; default prints the 5-section summary contract."""
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    request = SolveRequest.model_validate(_load_json(request_path))
    result = runtime.solve(request)
    if advanced:
        _dump(result.model_dump(mode="json"))  # 全量（含 advanced_view）
    else:
        from vencertia.presentation import solve_summary

        _dump(solve_summary(result), "summary")  # 默认 5 段合同


@app.command()
def demo() -> None:
    """Run the built-in B2B SaaS demo scenario (full closed loop)."""
    from examples.demo_b2b_saas_mvp import run_demo

    summary = run_demo(console=console)
    _dump(summary)


@app.command("quick-solve")
def quick_solve(problem: str | None = None, options_json: str | None = None) -> None:
    """三分钟快速决策：一条命令端到端，输出 5 段合同（轻量模式）。"""
    from vencertia.quick_solve import run_quick_solve

    opts = json.loads(options_json) if options_json else None
    _dump(run_quick_solve(problem_text=problem, options=opts), "summary")


# -- decision ---------------------------------------------------------------

decision_app = typer.Typer(help="Decision sub-commands")
app.add_typer(decision_app, name="decision")


@decision_app.command("compile")
def decision_compile(problem_json: Path, db: str | None = None) -> None:
    """Compile a decision from a problem JSON file."""
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    data = _load_json(problem_json)
    compiled = runtime.compiler.compile(
        data["problem_text"],
        {"project_id": data.get("project_id", "PRJ_CLI"), "user_id": data.get("user_id")},
        options=data.get("options"),
    )
    _dump(compiled.model_dump(mode="json"))


@decision_app.command("evaluate")
def decision_evaluate(decision_json: Path, db: str | None = None) -> None:
    """Evaluate a decision from a JSON file (options + beliefs inline)."""
    from vencertia.domain import Belief

    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    data = _load_json(decision_json)
    decision = Decision.model_validate(data["decision"])
    repo.save_decision(decision)
    if data.get("beliefs"):
        for belief_data in data["beliefs"]:
            repo.save_belief(Belief.model_validate(belief_data))
    result, convergence = runtime.evaluate_decision(decision.id)
    _dump(
        {
            "decision": result.model_dump(mode="json"),
            "convergence": convergence.model_dump(mode="json"),
        }
    )


@decision_app.command("sensitivity")
def decision_sensitivity(decision_id: str, db: str | None = None) -> None:
    """Compute and show decision sensitivity (flip thresholds + robustness)."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decision = repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    beliefs = repo.get_beliefs(decision.project_id)
    result = runtime.engines.decision_engine.evaluate(
        __import__(
            "vencertia.runtime.decision_engine", fromlist=["DecisionEngineInput"]
        ).DecisionEngineInput(
            decision=decision,
            beliefs=beliefs,
            risk_aversion=settings.risk_aversion,
            minimum_margin=settings.minimum_margin,
            max_critical_uncertainty=settings.max_critical_uncertainty,
            convergence_status="NOT_CONVERGED",
        )
    )
    sensitivity = runtime.engines.decision_sensitivity_engine.compute(decision, beliefs, result)
    repo.save_decision_sensitivity(sensitivity)
    _dump(sensitivity.model_dump(mode="json"))


@decision_app.command("trace")
def decision_trace(decision_id: str, db: str | None = None) -> None:
    """Show the persisted decision trace."""
    settings = _settings_with_db(db)
    _, repo = _default_runtime(settings)
    trace = repo.get_decision_trace(decision_id)
    if trace is None:
        console.print(f"[yellow]No decision trace for {decision_id}.[/yellow]")
        return
    _dump(trace.model_dump(mode="json"))


# -- evidence ---------------------------------------------------------------

evidence_app = typer.Typer(help="Evidence sub-commands")
app.add_typer(evidence_app, name="evidence")


@evidence_app.command("add")
def evidence_add(evidence_json: Path, db: str | None = None) -> None:
    """Add evidence (graded by the EvidencePolicy)."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    evidence = Evidence.model_validate(_load_json(evidence_json))
    grade = runtime.policy.grade(evidence)
    if grade.scope_gate == "REJECTED":
        console.print(f"[red]REJECTED: {grade.reason}[/red]")
        raise typer.Exit(code=1)
    graded = runtime.policy.apply_authority(evidence, settings.policy_version)
    repo.add_evidence(graded)
    _dump(graded.model_dump(mode="json"), "graded_evidence")


@evidence_app.command("bind")
def evidence_bind(evidence_id: str, db: str | None = None, auto_extract: bool = True) -> None:
    """Run the claim-binding pipeline for one evidence record."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    evidence = repo.get_evidence(evidence_id)
    if evidence is None:
        raise EntityNotFoundError("evidence", evidence_id)
    existing_claims = repo.list_claims()
    from vencertia.domain import ClaimBindingInput

    output = runtime.engines.claim_binding_engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "evidence_id": evidence.id,
                    "id": evidence.id,
                    "scope": evidence.scope.value if hasattr(evidence.scope, "value") else evidence.scope,
                    "evidence_type": evidence.evidence_type.value
                    if hasattr(evidence.evidence_type, "value")
                    else evidence.evidence_type,
                    "source": evidence.source,
                    "supports_or_contradicts": evidence.supports_or_contradicts.value
                    if hasattr(evidence.supports_or_contradicts, "value")
                    else evidence.supports_or_contradicts,
                    "directness": evidence.directness,
                    "reliability": evidence.reliability,
                    "relevance": evidence.relevance,
                    "strength": evidence.strength,
                    "authority_level": evidence.authority_level.value
                    if hasattr(evidence.authority_level, "value")
                    else evidence.authority_level,
                    "verification": evidence.verification.value
                    if hasattr(evidence.verification, "value")
                    else evidence.verification,
                }
            ],
            context={"claims": [c.model_dump(mode="json") for c in existing_claims]},
            existing_claims=[c.model_dump(mode="json") for c in existing_claims],
            auto_extract=auto_extract,
            binding_confidence_threshold=settings.binding_confidence_threshold,
        )
    )
    _dump(output.model_dump(mode="json"))


@evidence_app.command("import")
def evidence_import(path: Path, project: str | None = None, db: str | None = None) -> None:
    """Batch import evidence from a JSON array or JSONL file (policy-graded)."""
    from vencertia.runtime import EvidenceImporter

    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    importer = EvidenceImporter(
        repo=repo, policy=runtime.policy, dedup=runtime.engines.dedup_engine
    )
    items, invalid = EvidenceImporter.load_file(path)
    report = importer.import_batch(items, project_id=project)
    _dump({**report.model_dump(mode="json"), "invalid": invalid}, "evidence_import")


# -- research ---------------------------------------------------------------

research_app = typer.Typer(help="Research sub-commands")
app.add_typer(research_app, name="research")


@research_app.command("plan")
def research_plan(decision_id: str, db: str | None = None) -> None:
    """Generate a research plan for a decision."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decision = repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    beliefs = repo.get_beliefs(decision.project_id)
    criticals = runtime.engines.uncertainty_engine.rank(decision, beliefs)
    plan = runtime.engines.research_planner.plan(decision, beliefs, criticals, None)
    repo.save_research_plan(plan)
    _dump(plan.model_dump(mode="json"))


@research_app.command("run")
def research_run(decision_id: str, db: str | None = None) -> None:
    """Execute the latest research plan through the SHARED pipeline (P0-5).

    v1.1.2 semantic upgrade: runs the full research pipeline (search → dedup →
    claim binding → applied evidence → belief updates → conflicts → stop rule)
    via ResearchExecutionService — same implementation as solve and the API.
    """
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    decision = runtime.repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    service = runtime.engines.research_execution
    if service is None:
        console.print("[red]research_execution service not wired[/red]")
        raise typer.Exit(code=1)
    result = service.run_plan(decision_id)
    _dump(result.model_dump(mode="json"))


# -- experiments -------------------------------------------------------------

experiment_app = typer.Typer(help="Experiment sub-commands")
app.add_typer(experiment_app, name="experiment")


@experiment_app.command("propose")
def experiment_propose(decision_id: str, db: str | None = None) -> None:
    """Propose experiments for a decision (ABSTAIN -> ranked experiments)."""
    from vencertia.runtime.experiment_optimizer import ExperimentProposalInput

    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decision = repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    beliefs = repo.get_beliefs(decision.project_id)
    criticals = runtime.engines.uncertainty_engine.rank(decision, beliefs)
    proposal = runtime.engines.experiment_optimizer.propose(
        ExperimentProposalInput(
            decision=decision,
            beliefs=beliefs,
            critical_belief_id=criticals[0].belief_id if criticals else None,
            candidates=repo.list_experiments(decision.project_id),
        )
    )
    _dump(
        {
            "decision_insufficient": proposal.decision_insufficient,
            "reason": proposal.reason,
            "ranked": [r.model_dump(mode="json") for r in proposal.ranked],
            "rejected": proposal.rejected,
        }
    )


# -- outcomes ----------------------------------------------------------------

outcome_app = typer.Typer(help="Outcome sub-commands")
app.add_typer(outcome_app, name="outcome")


@outcome_app.command("record")
def outcome_record(action_id: str, result: str, db: str | None = None, outcome_type: str = "PARTIAL") -> None:
    """Record an outcome for an action; triggers the closed loop."""
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    recorded = runtime.record_outcome(
        action_id, result, outcome_type=OutcomeType(outcome_type.upper())
    )
    _dump(recorded.model_dump(mode="json"))


# -- predictions --------------------------------------------------------------

prediction_app = typer.Typer(help="Prediction sub-commands")
app.add_typer(prediction_app, name="prediction")


@prediction_app.command("create")
def prediction_create(decision_id: str, db: str | None = None) -> None:
    """Create prediction entries for a decision's relevant beliefs."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decision = repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    beliefs = repo.get_beliefs(decision.project_id)
    entries = runtime.engines.prediction_ledger.register(decision, beliefs)
    # M0-4: single persistence point — register() no longer saves.
    for entry in entries:
        repo.save_prediction(entry)
    _dump([e.model_dump(mode="json") for e in entries])


@prediction_app.command("resolve")
def prediction_resolve(prediction_id: str, outcome: int, db: str | None = None) -> None:
    """Resolve a prediction (outcome: 0 or 1)."""
    if outcome not in (0, 1):
        raise typer.BadParameter("outcome must be 0 or 1")
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    entry = runtime.engines.prediction_ledger.resolve(prediction_id, bool(outcome))
    _dump(entry.model_dump(mode="json"))


# -- belief ---------------------------------------------------------------------

belief_app = typer.Typer(help="Belief sub-commands")
app.add_typer(belief_app, name="belief")


@belief_app.command("history")
def belief_history(belief_id: str, db: str | None = None) -> None:
    """Show the belief-update record history for one belief."""
    settings = _settings_with_db(db)
    _, repo = _default_runtime(settings)
    records = repo.list_belief_update_records(belief_id)
    if not records:
        console.print(f"[yellow]No update records for {belief_id}.[/yellow]")
        return
    _dump([r.model_dump(mode="json") for r in records])


# -- calibration ---------------------------------------------------------------

calibration_app = typer.Typer(help="Calibration sub-commands")
app.add_typer(calibration_app, name="calibration")


@calibration_app.command("report")
def calibration_report(scope: str = "ALL", key: str = "ALL", db: str | None = None) -> None:
    """Print the calibration report (scope: ALL|MODEL|DOMAIN|MODULE)."""
    from vencertia.domain import CalibrationScope
    from vencertia.presentation import calibration_summary
    from vencertia.runtime.calibration_engine import CalibrationInput

    settings = _settings_with_db(db)
    _, repo = _default_runtime(settings)
    runtime = SolveOrchestrator(repo=repo, settings=settings)
    profile = runtime.engines.calibration_engine.report(
        CalibrationInput(repo.list_predictions(), CalibrationScope(scope.upper()), key, settings.ece_bins)
    )
    _dump(calibration_summary(profile), "calibration")


# -- benchmark ------------------------------------------------------------------

benchmark_app = typer.Typer(help="Benchmark sub-commands")
app.add_typer(benchmark_app, name="benchmark")


@benchmark_app.command("run")
def benchmark_run(level: str = "L0", path: Path | None = None, db: str | None = None) -> None:
    """Run L0, L1, L2 or CLAIM_BINDING benchmarks."""
    from vencertia.benchmark.claim_binding import ClaimBindingBenchmarkRunner
    from vencertia.benchmark.l0 import L0Runner
    from vencertia.benchmark.l1 import L1Runner

    root = Path(__file__).resolve().parents[2]
    if level.upper() == "L0":
        runner = L0Runner()
        new_report = runner.run_file(path or root / "data/benchmarks/l0_cases.json")
        legacy_report = runner.run_legacy_file(root / "data/benchmarks/v0.2.jsonl")
        combined = {
            "new_l0": new_report.model_dump(mode="json"),
            "legacy_v0_2": legacy_report.model_dump(mode="json"),
        }
        _dump(combined)
        if new_report.failed:
            raise typer.Exit(code=1)
    elif level.upper() == "L1":
        runner = L1Runner()
        report = runner.run(path or root / "data/benchmarks/l1_cases.jsonl")
        _dump(report.model_dump(mode="json"))
        if report.rejected:
            console.print(f"[yellow]Rejected (leakage audit failed): {report.rejected}[/yellow]")
        if report.failed:
            raise typer.Exit(code=1)
    elif level.upper() == "L2":
        from vencertia.benchmark.l2 import L2Runner

        settings = _settings_with_db(db)
        _, repo = _default_runtime(settings)  # 复用 container 单根接线
        runner = L2Runner(repo=repo)  # repo 非 None → 真实 due_report
        report = runner.due_report()
        if not report:
            console.print(
                "[yellow]L2 前瞻预测库为空：需先 register 前瞻预测（参见 docs/benchmark.md）。[/yellow]"
            )
            return
        _dump([e.model_dump(mode="json") for e in report])
    elif level.upper() in ("BINDING", "CLAIM_BINDING", "CB"):
        runner = ClaimBindingBenchmarkRunner()
        report = runner.run(path or root / "data/benchmarks/claim_binding_cases.json")
        print(runner.render(report))
        # Known limitations are reported but do not fail the gate; unexpected
        # failures do.
        failed = [r for r in report.cases if not r.correct and not r.known_limitation]
        if failed:
            raise typer.Exit(code=1)
    else:
        raise typer.BadParameter("level must be L0, L1, L2 or CLAIM_BINDING")


# -- project ---------------------------------------------------------------------

project_app = typer.Typer(help="Project sub-commands")
app.add_typer(project_app, name="project")


@project_app.command("beliefs")
def project_beliefs(project_id: str, db: str | None = None) -> None:
    """List beliefs for a project (rich table)."""
    settings = _settings_with_db(db)
    _, repo = _default_runtime(settings)
    beliefs = repo.get_beliefs(project_id)
    table = Table(title=f"Beliefs: {project_id}")
    table.add_column("id")
    table.add_column("statement")
    table.add_column("p")
    table.add_column("unc")
    table.add_column("α")
    table.add_column("β")
    table.add_column("pv")
    for b in beliefs:
        table.add_row(
            b.id,
            b.statement,
            f"{b.probability:.3f}",
            f"{b.uncertainty:.3f}",
            f"{b.alpha:.2f}",
            f"{b.beta:.2f}",
            str(b.posterior_version),
        )
    console.print(table)


@app.command()
def uncertainties(project_id: str, db: str | None = None) -> None:
    """List decision-critical uncertainties for a project."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decisions = repo.list_decisions(project_id)
    if not decisions:
        console.print("[yellow]No decisions for project.[/yellow]")
        return
    latest = max(decisions, key=lambda d: d.updated_at)
    beliefs = repo.get_beliefs(project_id)
    criticals = runtime.engines.uncertainty_engine.rank(latest, beliefs)
    _dump([c.model_dump(mode="json") for c in criticals])


# -- migration ---------------------------------------------------------------------

@app.command("migrate-v10.2")
def migrate_v10_2(
    source: Path,
    db: str | None = None,
    dry_run: bool = False,
) -> None:
    """Import assets from an AgentV10.2 Full Release directory."""
    from vencertia.legacy.import_v10_2 import V10_2Importer
    from vencertia.repositories.sqlite import SQLiteRepository

    settings = _settings_with_db(db)
    repo = SQLiteRepository(settings.db_dsn)
    importer = V10_2Importer(source_dir=source, repo=repo)
    report = importer.dry_run() if dry_run else importer.import_all()
    table = Table(title=f"V10.2 import ({'dry-run' if dry_run else 'import'})")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Source", report.manifest.source_dir)
    table.add_row("Found", str(report.manifest.total))
    table.add_row("Imported", str(report.imported))
    table.add_row("Skipped (dup)", str(report.skipped_duplicates))
    table.add_row("Failed", str(report.failed))
    table.add_row("Coverage", f"{report.coverage:.1%}")
    console.print(table)
    for warning in report.warnings:
        console.print(f"[yellow]warn: {warning}[/yellow]")


if __name__ == "__main__":
    app()
