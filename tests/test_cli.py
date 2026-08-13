"""CLI smoke tests: core commands load and execute against a temp DB."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from vencertia.cli import app

runner = CliRunner()


def _tmp_db(tmp_path) -> str:
    return str(tmp_path / "cli.db")


def test_cli_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "Vencertia" in r.output


def test_cli_solve(tmp_path):
    req = {
        "project_id": "PRJ_CLI", "problem_text": "Should we commit six weeks to the MVP?",
        "user_id": "u1",
    }
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req))
    r = runner.invoke(app, ["solve", str(req_path), "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output


def test_cli_solve_default_prints_summary(tmp_path):
    """T2: default CLI solve prints the 5-section summary contract."""
    req = {
        "project_id": "PRJ_CLI_SUM", "problem_text": "Should we commit six weeks to the MVP?",
        "user_id": "u1",
    }
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req))
    r = runner.invoke(app, ["solve", str(req_path), "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert "current_judgment" in payload


def test_cli_solve_advanced_prints_full(tmp_path):
    """T2: --advanced still dumps the full projection including advanced_view."""
    req = {
        "project_id": "PRJ_CLI_ADV", "problem_text": "Should we commit six weeks to the MVP?",
        "user_id": "u1",
    }
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req))
    r = runner.invoke(
        app, ["solve", str(req_path), "--db", _tmp_db(tmp_path), "--advanced"]
    )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert "advanced_view" in payload


def test_cli_decision_compile(tmp_path):
    problem = {"problem_text": "Should we build the MVP?", "project_id": "PRJ_CLI", "user_id": "u1"}
    p = tmp_path / "problem.json"
    p.write_text(json.dumps(problem))
    r = runner.invoke(app, ["decision", "compile", str(p), "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output


def test_cli_evidence_add(tmp_path):
    evidence = {"id": "E_CLI1", "scope": "PROJECT", "evidence_type": "REAL_PAYMENT",
                "source": "paid 100", "claim_ids": ["CLM_WTP"],
                # v1.1.2 (P0-3): PROJECT evidence must carry project_id.
                "project_id": "PRJ_CLI"}
    p = tmp_path / "evidence.json"
    p.write_text(json.dumps(evidence))
    r = runner.invoke(app, ["evidence", "add", str(p), "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output


def test_cli_project_beliefs_empty(tmp_path):
    r = runner.invoke(app, ["project", "beliefs", "PRJ_NONE", "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0


def test_cli_uncertainties_empty(tmp_path):
    r = runner.invoke(app, ["uncertainties", "PRJ_NONE", "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0


def test_cli_calibration_report(tmp_path):
    r = runner.invoke(app, ["calibration", "report", "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0


def test_cli_prediction_resolve_bad_outcome(tmp_path):
    r = runner.invoke(app, ["prediction", "resolve", "PRD_X", "5", "--db", _tmp_db(tmp_path)])
    assert r.exit_code != 0  # invalid outcome


def test_cli_migrate_dry_run(tmp_path):
    source = (
        tmp_path
        / "legacy"
        / "agent_v10_2"
        / "AgentV10.2"
        / "Vencertia_AgentV10.2_Full_Release"
    )
    # Point at the real release dir for a meaningful dry-run.
    import pathlib

    real = pathlib.Path(__file__).resolve().parents[1] / "legacy" / "agent_v10_2" / "AgentV10.2" / "Vencertia_AgentV10.2_Full_Release"
    if not real.exists():
        source.mkdir(parents=True)
    else:
        source = real
    r = runner.invoke(app, ["migrate-v10.2", str(source), "--db", _tmp_db(tmp_path), "--dry-run"])
    assert r.exit_code == 0, r.output


def test_cli_l2_empty_hint(tmp_path):
    """T4: empty L2 registry prints a "需先 register" hint, not a bare []."""
    r = runner.invoke(app, ["benchmark", "run", "--level", "L2", "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "需先 register" in r.output


def test_cli_l2_with_due_prediction(tmp_path):
    """T4: with a due prediction, L2 outputs the real due_report (contains id)."""
    from vencertia.config import Settings
    from vencertia.container import build_container
    from vencertia.domain import PredictionEntry

    db = _tmp_db(tmp_path)
    repo = build_container(Settings(db_dsn=f"sqlite:///{db}")).repository
    repo.save_prediction(
        PredictionEntry(
            id="PRD_DUE", project_id="PRJ_L2", target="will we ship?",
            predicted_probability=0.6,
        )
    )
    r = runner.invoke(app, ["benchmark", "run", "--level", "L2", "--db", db])
    assert r.exit_code == 0, r.output
    assert "PRD_DUE" in r.output


def test_python_m_vencertia_help():
    """T4: ``python -m vencertia --help`` is equivalent to the CLI entry point."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "vencertia", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Vencertia" in proc.stdout
