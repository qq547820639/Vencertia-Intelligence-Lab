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


def test_cli_decision_compile(tmp_path):
    problem = {"problem_text": "Should we build the MVP?", "project_id": "PRJ_CLI", "user_id": "u1"}
    p = tmp_path / "problem.json"
    p.write_text(json.dumps(problem))
    r = runner.invoke(app, ["decision", "compile", str(p), "--db", _tmp_db(tmp_path)])
    assert r.exit_code == 0, r.output


def test_cli_evidence_add(tmp_path):
    evidence = {"id": "E_CLI1", "scope": "PROJECT", "evidence_type": "REAL_PAYMENT",
                "source": "paid 100", "claim_ids": ["CLM_WTP"]}
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
