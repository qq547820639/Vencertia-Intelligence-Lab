"""Vencertia v1.0 CLI (typer + rich, fully parameterized, non-interactive)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vencertia.config import Settings, get_settings
from vencertia.domain import Decision, Evidence, OutcomeType
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle

app = typer.Typer(help="Vencertia Adaptive Decision System v1.0")
console = Console()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(data, label: str = "result") -> None:
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def _settings_with_db(db: Optional[str]) -> Settings:
    settings = get_settings()
    if db:
        d = settings.__dict__.copy()
        d["db_dsn"] = f"sqlite:///{db}"
        return Settings(**d)
    return settings


def _default_runtime(settings: Settings) -> tuple[SolveOrchestrator, Repository]:
    repo = SQLiteRepository(settings.db_dsn)
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
    return runtime, repo


# ---------------------------------------------------------------------------


@app.command()
def solve(request_path: Path, db: Optional[str] = None) -> None:
    """Run the full solve loop from a request JSON file."""
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    request = SolveRequest.model_validate(_load_json(request_path))
    result = runtime.solve(request)
    _dump(result.model_dump(mode="json"))


@app.command()
def demo() -> None:
    """Run the built-in B2B SaaS demo scenario (full closed loop)."""
    from examples.demo_b2b_saas_mvp import run_demo

    summary = run_demo(console=console)
    _dump(summary)


# -- decision ---------------------------------------------------------------

decision_app = typer.Typer(help="Decision sub-commands")
app.add_typer(decision_app, name="decision")


@decision_app.command("compile")
def decision_compile(problem_json: Path, db: Optional[str] = None) -> None:
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
def decision_evaluate(decision_json: Path, db: Optional[str] = None) -> None:
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


# -- evidence ---------------------------------------------------------------

evidence_app = typer.Typer(help="Evidence sub-commands")
app.add_typer(evidence_app, name="evidence")


@evidence_app.command("add")
def evidence_add(evidence_json: Path, db: Optional[str] = None) -> None:
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


# -- experiments -------------------------------------------------------------

experiment_app = typer.Typer(help="Experiment sub-commands")
app.add_typer(experiment_app, name="experiment")


@experiment_app.command("propose")
def experiment_propose(decision_id: str, db: Optional[str] = None) -> None:
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
        }
    )


# -- outcomes ----------------------------------------------------------------

outcome_app = typer.Typer(help="Outcome sub-commands")
app.add_typer(outcome_app, name="outcome")


@outcome_app.command("record")
def outcome_record(action_id: str, result: str, db: Optional[str] = None, outcome_type: str = "PARTIAL") -> None:
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
def prediction_create(decision_id: str, db: Optional[str] = None) -> None:
    """Create prediction entries for a decision's relevant beliefs."""
    settings = _settings_with_db(db)
    runtime, repo = _default_runtime(settings)
    decision = repo.get_decision(decision_id)
    if decision is None:
        raise EntityNotFoundError("decision", decision_id)
    beliefs = repo.get_beliefs(decision.project_id)
    entries = runtime.engines.prediction_ledger.register(decision, beliefs)
    _dump([e.model_dump(mode="json") for e in entries])


@prediction_app.command("resolve")
def prediction_resolve(prediction_id: str, outcome: int, db: Optional[str] = None) -> None:
    """Resolve a prediction (outcome: 0 or 1)."""
    if outcome not in (0, 1):
        raise typer.BadParameter("outcome must be 0 or 1")
    settings = _settings_with_db(db)
    runtime, _ = _default_runtime(settings)
    entry = runtime.engines.prediction_ledger.resolve(prediction_id, bool(outcome))
    _dump(entry.model_dump(mode="json"))


# -- calibration ---------------------------------------------------------------

calibration_app = typer.Typer(help="Calibration sub-commands")
app.add_typer(calibration_app, name="calibration")


@calibration_app.command("report")
def calibration_report(scope: str = "ALL", key: str = "ALL", db: Optional[str] = None) -> None:
    """Print the calibration report (scope: ALL|MODEL|DOMAIN|MODULE)."""
    from vencertia.domain import CalibrationScope
    from vencertia.runtime.calibration_engine import CalibrationInput

    settings = _settings_with_db(db)
    _, repo = _default_runtime(settings)
    runtime = SolveOrchestrator(repo=repo, settings=settings)
    profile = runtime.engines.calibration_engine.report(
        CalibrationInput(repo.list_predictions(), CalibrationScope(scope.upper()), key, settings.ece_bins)
    )
    table = Table(title=f"Calibration {scope}:{key}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("n", str(profile.n))
    table.add_row("Brier", f"{profile.brier_score}" if profile.brier_score is not None else "-")
    table.add_row("ECE", f"{profile.expected_calibration_error}" if profile.expected_calibration_error is not None else "-")
    table.add_row("Mean confidence", f"{profile.mean_confidence}" if profile.mean_confidence is not None else "-")
    table.add_row("Empirical rate", f"{profile.empirical_rate}" if profile.empirical_rate is not None else "-")
    console.print(table)


# -- benchmark ------------------------------------------------------------------

benchmark_app = typer.Typer(help="Benchmark sub-commands")
app.add_typer(benchmark_app, name="benchmark")


@benchmark_app.command("run")
def benchmark_run(level: str = "L0", path: Optional[Path] = None) -> None:
    """Run L0 (synthetic) or L1 (time-sliced) benchmarks."""
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
    else:
        raise typer.BadParameter("level must be L0 or L1")


# -- project ---------------------------------------------------------------------

project_app = typer.Typer(help="Project sub-commands")
app.add_typer(project_app, name="project")


@project_app.command("beliefs")
def project_beliefs(project_id: str, db: Optional[str] = None) -> None:
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
    for b in beliefs:
        table.add_row(b.id, b.statement, f"{b.probability:.3f}", f"{b.uncertainty:.3f}", f"{b.alpha:.2f}", f"{b.beta:.2f}")
    console.print(table)


@app.command()
def uncertainties(project_id: str, db: Optional[str] = None) -> None:
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
    db: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Import assets from an AgentV10.2 Full Release directory."""
    from vencertia.legacy.import_v10_2 import V10_2Importer

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
