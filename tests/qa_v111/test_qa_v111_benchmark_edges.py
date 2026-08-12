"""QA v1.1.1 Iteration 2 — adversarial edge cases for Claim Binding Benchmark.

Targets (QA task list):
 11. benchmark division-by-zero: empty dataset / zero gold / zero prediction
     → explicit N/A (None) or 0.0
 13. zero predicted binding / zero gold binding
 14. all-unbound / all-ambiguous extreme inputs
 15. empty benchmark dataset
"""

from __future__ import annotations

from vencertia.benchmark.claim_binding import ClaimBindingBenchmarkRunner, _safe_ratio


def _case(cid: str, category: str, gold_status: str, source: str = "text",
          gold_claim_ids: list[str] | None = None,
          claims: list[dict] | None = None,
          scope: str = "MARKET",
          config: dict | None = None) -> dict:
    claims = claims or [
        {"id": "CLM_1", "statement": "ICP will pay for the promised outcome", "scope": "PROJECT"}
    ]
    return {
        "id": cid,
        "category": category,
        "evidence": {"id": f"E_{cid}", "scope": scope, "source": source},
        "claims": claims,
        "gold_status": gold_status,
        "gold_claim_ids": gold_claim_ids or [],
        "config": config or {},
    }


def test_safe_ratio_zero_denominator_is_none_not_zero():
    assert _safe_ratio(0, 0) is None  # N/A, never faked as 0.0
    assert _safe_ratio(3, 0) is None
    assert _safe_ratio(0, 3) == 0.0  # explicit zero when denominator exists


def test_empty_dataset_renders_na_not_crash():
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases([])
    assert report.n == 0
    assert report.metrics["coverage"] is None  # 0/0 → N/A
    assert report.metrics["precision"] is None
    assert report.metrics["recall"] is None
    assert report.metrics["f1"] is None
    text = runner.render(report)
    assert "N/A" in text


def test_all_ambiguous_inputs_report_na_for_bound_metrics():
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases(
        [
            _case("CB-A1", "ambiguous", "AMBIGUOUS", source="same words for two claims"),
            _case("CB-A2", "ambiguous", "AMBIGUOUS", source="same words for two claims"),
        ]
    )
    # Zero BOUND gold → precision/recall/f1 zero-denominator → N/A.
    assert report.metrics["precision"] is None
    assert report.metrics["recall"] is None
    assert report.metrics["f1"] is None
    # Ambiguous accuracy has a denominator → real number.
    assert report.metrics["ambiguous_accuracy"] is not None
    # Multi-claim metrics N/A (no BOUND gold with >=2 ids).
    assert report.metrics["multi_claim_exact_match"] is None
    assert report.metrics["multi_claim_partial_match"] is None


def test_all_unbound_inputs_report_unbound_accuracy():
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases(
        [
            _case("CB-U1", "irrelevant", "UNBOUND_EVIDENCE", source="completely unrelated macro"),
            _case("CB-U2", "irrelevant", "UNBOUND_EVIDENCE", source="no relation at all"),
        ]
    )
    assert report.metrics["unbound_accuracy"] == 1.0
    assert report.metrics["precision"] is None  # zero BOUND gold
    assert report.metrics["coverage"] == 1.0


def test_zero_predicted_binding_single_bound_gold_is_precision_na():
    """One gold BOUND but engine predicts nothing → tp=0, fp=0 → precision
    denominator (tp+fp)=0 → N/A; recall 0/1 = 0.0."""
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases(
        [
            _case(
                "CB-ZP1", "weak_lexical_overlap", "BOUND",
                source="global macro commentary about interest rates",
                gold_claim_ids=["CLM_1"],
            )
        ]
    )
    # The extractor likely yields no candidate at all → UNBOUND prediction.
    assert report.cases[0].predicted_status == "UNBOUND_EVIDENCE"
    assert report.metrics["precision"] is None  # tp+fp == 0 → N/A
    assert report.metrics["recall"] == 0.0      # tp+fn == 1 → real zero
    assert report.metrics["f1"] is None


def test_single_case_bound_metrics_real():
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases(
        [
            _case(
                "CB-OK1", "single_match", "BOUND",
                source="ICP will pay for the promised outcome",
                gold_claim_ids=["CLM_1"],
            )
        ]
    )
    assert report.cases[0].predicted_status == "BOUND"
    assert report.metrics["precision"] == 1.0
    assert report.metrics["recall"] == 1.0
    assert report.metrics["f1"] == 1.0
    assert report.metrics["coverage"] == 1.0
