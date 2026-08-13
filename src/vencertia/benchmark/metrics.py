"""Benchmark metrics — pure functions (docs/benchmark.md).

All metrics are deterministic and operate on simple lists so they can be
unit-tested without any runtime wiring.
"""

from __future__ import annotations

from typing import Any


def compute_decision_accuracy(predicted: list[str], gold: list[str]) -> float:
    """Fraction of decisions where the predicted option equals the gold option."""
    if not gold:
        return 0.0
    correct = sum(1 for p, g in zip(predicted, gold) if p == g)
    return correct / len(gold)


def compute_abstention_quality(decided: list[bool], correct: list[bool]) -> dict:
    """Abstention quality: coverage x selective accuracy (ADR-007).

    ``decided[i]`` is True when the system committed to an option; ``correct[i]``
    is True when the committed option was right (only meaningful when decided).
    """
    n = len(decided)
    if n == 0:
        return {"coverage": 0.0, "selective_accuracy": 0.0, "quality": 0.0, "n": 0}
    coverage = sum(1 for d in decided if d) / n
    decided_correct = [
        correct[i] for i in range(n) if decided[i] and i < len(correct)
    ]
    selective = (
        sum(1 for c in decided_correct if c) / len(decided_correct)
        if decided_correct
        else 0.0
    )
    return {
        "coverage": round(coverage, 6),
        "selective_accuracy": round(selective, 6),
        "quality": round(coverage * selective, 6),
        "n": n,
    }


def compute_brier(preds: list[float], outcomes: list[int]) -> float:
    """Mean squared error between probabilities and binary outcomes."""
    if not preds:
        return 0.0
    return sum((p - o) ** 2 for p, o in zip(preds, outcomes)) / len(preds)


def compute_ece(preds: list[float], outcomes: list[int], bins: int = 10) -> float:
    """Expected calibration error with equal-width bins over [0,1]."""
    if not preds:
        return 0.0
    n = len(preds)
    ece = 0.0
    for i in range(bins):
        lo = i / bins
        hi = (i + 1) / bins
        bucket = [
            (p, o)
            for p, o in zip(preds, outcomes)
            if lo <= p < hi or (i == bins - 1 and p == 1.0)
        ]
        if not bucket:
            continue
        conf = sum(x[0] for x in bucket) / len(bucket)
        rate = sum(x[1] for x in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(conf - rate)
    return ece


def compute_experiment_selection_accuracy(predicted: list[str], gold: list[str]) -> float:
    if not gold:
        return 0.0
    return sum(1 for p, g in zip(predicted, gold) if p == g) / len(gold)


def compute_critical_uncertainty_accuracy(predicted: list[str], gold: list[str]) -> float:
    if not gold:
        return 0.0
    return sum(1 for p, g in zip(predicted, gold) if p == g) / len(gold)


def compute_evidence_precision_recall(hits: int, predicted: int, relevant: int) -> dict:
    """Precision/recall/F1 for evidence retrieval."""
    precision = hits / predicted if predicted else 0.0
    recall = hits / relevant if relevant else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "hits": hits,
        "predicted": predicted,
        "relevant": relevant,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def compute_decision_regret(chosen: list[float | None], best: list[float | None]) -> float | None:
    """Average utility loss of the chosen option vs the best option.

    v1.1.2 (P1-10): ``None`` utilities are treated as "no utility label" and
    excluded from the average. When NO usable pair exists the function returns
    ``None`` (N/A) — it never fabricates a fake 0 regret.
    """
    pairs = [
        (c, b)
        for c, b in zip(chosen, best)
        if c is not None and b is not None
    ]
    if not pairs:
        return None
    regrets = [max(b - c, 0.0) for c, b in pairs]
    return round(sum(regrets) / len(regrets), 6)


# -- v1.1 metrics ------------------------------------------------------------
# N/A semantics: functions return None when the required data is missing so
# reports can display "N/A" instead of fabricating a number.


def compute_claim_binding_accuracy(hits: int, predicted: int, relevant: int) -> dict | None:
    """Precision/recall/F1 of evidence→claim binding (L1: Claim Binding Accuracy)."""
    if predicted <= 0 or relevant <= 0:
        return None
    precision = hits / predicted
    recall = hits / relevant
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "hits": hits,
        "predicted": predicted,
        "relevant": relevant,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def compute_research_efficiency(
    queries: list[int], evidence: list[int], time: list[float]
) -> dict | None:
    """Evidence-per-query and evidence-per-day across research rounds."""
    if not queries or sum(queries) <= 0 or not time:
        return None
    return {
        "rounds": len(queries),
        "total_queries": sum(queries),
        "total_evidence": sum(evidence),
        "evidence_per_query": round(sum(evidence) / max(1, sum(queries)), 6),
        "evidence_per_day": round(sum(evidence) / max(1e-6, sum(time)), 6),
    }


def compute_evidence_yield(new_evidence: int, retrieved: int) -> float | None:
    """Fraction of retrieved items that became new (non-duplicate) evidence."""
    if retrieved <= 0:
        return None
    return round(new_evidence / retrieved, 6)


def compute_belief_delta_quality(deltas: list[float], gold_deltas: list[float]) -> dict | None:
    """Correlation-style agreement between predicted and gold belief deltas."""
    if not deltas or len(deltas) != len(gold_deltas):
        return None
    n = len(deltas)
    if n == 0:
        return None
    mae = sum(abs(a - b) for a, b in zip(deltas, gold_deltas)) / n
    return {
        "n": n,
        "mae": round(mae, 6),
        "direction_agreement": round(
            sum(1 for a, b in zip(deltas, gold_deltas) if (a >= 0) == (b >= 0)) / n, 6
        ),
    }


def compute_decision_change_precision(flips_predicted: list[bool], flips_actual: list[bool]) -> float | None:
    """Precision of predicted recommendation flips vs actual flips."""
    if not flips_predicted:
        return None
    hits = sum(1 for p, a in zip(flips_predicted, flips_actual) if p and a)
    predicted_positives = sum(1 for p in flips_predicted if p)
    if predicted_positives <= 0:
        return None
    return round(hits / predicted_positives, 6)


def compute_all(
    cases: list[dict],
    predictions: list[dict] | None = None,
) -> dict[str, Any]:
    """Compute the full metric set from a list of case result dicts.

    Each case dict may include: predicted_option, gold_option, decided,
    correct, predicted_experiment, gold_experiment, predicted_critical,
    gold_critical, evidence_hits, evidence_predicted, evidence_relevant,
    chosen_utility, best_utility. Predictions (for Brier/ECE) are separate.

    v1.1.2 (P1-10) metric semantics:
    - ``policy_regression_pass_rate`` = full-case pass rate (existing gate
      metric; computed over ALL cases).
    - ``decision_option_accuracy`` = option accuracy over cases whose
      ``gold_option`` is a real option id (``gold_option_id=None`` /
      "NO_DECISION" cases are EXCLUDED from the denominator).
    - ``decision_status_accuracy`` = status accuracy over cases with a
      ``gold_status``.
    - ``decision_accuracy`` is kept as a backward-compatible alias of
      ``decision_option_accuracy``.
    """
    predicted = [c.get("predicted_option", "NO_DECISION") for c in cases]
    gold = [c.get("gold_option", "NO_DECISION") for c in cases]
    decided = [c.get("decided", c.get("predicted_option") != "NO_DECISION") for c in cases]
    correct = [c.get("correct", False) for c in cases]

    exp_pred = [c.get("predicted_experiment", "") for c in cases if c.get("gold_experiment")]
    exp_gold = [c.get("gold_experiment") for c in cases if c.get("gold_experiment")]
    crit_pred = [c.get("predicted_critical", "") for c in cases if c.get("gold_critical")]
    crit_gold = [c.get("gold_critical") for c in cases if c.get("gold_critical")]

    evidence_metric: dict[str, Any] = {}
    if cases and "evidence_predicted" in cases[0]:
        evidence_metric = compute_evidence_precision_recall(
            hits=sum(c.get("evidence_hits", 0) for c in cases),
            predicted=sum(c.get("evidence_predicted", 0) for c in cases),
            relevant=sum(c.get("evidence_relevant", 0) for c in cases),
        )

    chosen = [c.get("chosen_utility") for c in cases]
    best = [c.get("best_utility") for c in cases]

    preds = [p["probability"] for p in (predictions or []) if p.get("settled")]
    outcomes = [1 if p.get("outcome") else 0 for p in (predictions or []) if p.get("settled")]

    # v1.1.2 (P1-10): split option/status accuracy — unlabeled cases are
    # excluded from the option-accuracy denominator.
    option_cases = [
        (p, g)
        for p, g in zip(predicted, gold)
        if g not in (None, "", "NO_DECISION")
    ]
    option_accuracy = (
        round(
            compute_decision_accuracy(
                [p for p, _ in option_cases], [g for _, g in option_cases]
            ),
            6,
        )
        if option_cases
        else None
    )
    status_cases = [
        (c.get("predicted_status"), c.get("gold_status"))
        for c in cases
        if c.get("gold_status")
    ]
    status_accuracy = (
        round(
            compute_decision_accuracy(
                [p for p, _ in status_cases], [g for _, g in status_cases]
            ),
            6,
        )
        if status_cases
        else None
    )

    regret = compute_decision_regret(chosen, best)

    return {
        "n_cases": len(cases),
        "policy_regression_pass_rate": round(
            sum(1 for c in correct if c) / len(correct), 6
        )
        if correct
        else 0.0,
        "decision_option_accuracy": option_accuracy,
        "decision_status_accuracy": status_accuracy,
        # Backward-compatible alias (v1.1.2 semantic: option accuracy only).
        "decision_accuracy": option_accuracy,
        "abstention_quality": compute_abstention_quality(decided, correct),
        "experiment_selection_accuracy": round(
            compute_experiment_selection_accuracy(exp_pred, exp_gold), 6
        )
        if exp_gold
        else None,
        "critical_uncertainty_accuracy": round(
            compute_critical_uncertainty_accuracy(crit_pred, crit_gold), 6
        )
        if crit_gold
        else None,
        "evidence_precision_recall": evidence_metric,
        "decision_regret": regret,
        "brier": round(compute_brier(preds, outcomes), 6) if preds else None,
        "ece": round(compute_ece(preds, outcomes), 6) if preds else None,
    }
