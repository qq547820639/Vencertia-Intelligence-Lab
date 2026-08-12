"""End-to-end demo test: B2B SaaS closed loop."""

from __future__ import annotations

from examples.demo_b2b_saas_mvp import run_demo


def test_demo_closed_loop():
    summary = run_demo()
    assert summary["decision_status"] == "ABSTAIN"
    assert "DO NOT COMMIT" in summary["verdict"]
    assert summary["critical_belief"] == "wtp"
    assert "paid" in (summary["next_experiment"] or "").lower()
    assert summary["wtp_after"] < summary["wtp_before"]
    assert summary["predictions_resolved"] >= 1
    assert summary["calibration"] is not None
    assert summary["total_events"] > 0
