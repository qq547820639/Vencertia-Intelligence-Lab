"""Benchmark metrics — pure functions (docs/BENCHMARK.md).

All metrics are deterministic and operate on simple lists so they can be
unit-tested without any runtime wiring.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def compute_decision_regret(chosen: list[float], best: list[float]) -> float:
    """Average utility loss of the chosen option vs the best option."""
    if not chosen:
        return 0.0
    regrets = [max(b - c, 0.0) for c, b in zip(chosen, best)]
    return round(sum(regrets) / len(regrets), 6)


def compute_all(
    cases: list[dict],
    predictions: Optional[list[dict]] = None,
) -> Dict[str, Any]:
    """Compute the full metric set from a list of case result dicts.

    Each case dict may include: predicted_option, gold_option, decided,
    correct, predicted_experiment, gold_experiment, predicted_critical,
    gold_critical, evidence_hits, evidence_predicted, evidence_relevant,
    chosen_utility, best_utility. Predictions (for Brier/ECE) are separate.
    """
    predicted = [c.get("predicted_option", "NO_DECISION") for c in cases]
    gold = [c.get("gold_option", "NO_DECISION") for c in cases]
    decided = [c.get("decided", c.get("predicted_option") != "NO_DECISION") for c in cases]
    correct = [c.get("correct", False) for c in cases]

    exp_pred = [c.get("predicted_experiment", "") for c in cases if c.get("gold_experiment")]
    exp_gold = [c.get("gold_experiment") for c in cases if c.get("gold_experiment")]
    crit_pred = [c.get("predicted_critical", "") for c in cases if c.get("gold_critical")]
    crit_gold = [c.get("gold_critical") for c in cases if c.get("gold_critical")]

    evidence_metric: Dict[str, Any] = {}
    if cases and "evidence_predicted" in cases[0]:
        evidence_metric = compute_evidence_precision_recall(
            hits=sum(c.get("evidence_hits", 0) for c in cases),
            predicted=sum(c.get("evidence_predicted", 0) for c in cases),
            relevant=sum(c.get("evidence_relevant", 0) for c in cases),
        )

    chosen = [c.get("chosen_utility", 0.0) for c in cases]
    best = [c.get("best_utility", 0.0) for c in cases]

    preds = [p["probability"] for p in (predictions or []) if p.get("settled")]
    outcomes = [1 if p.get("outcome") else 0 for p in (predictions or []) if p.get("settled")]

    return {
        "n_cases": len(cases),
        "decision_accuracy": round(compute_decision_accuracy(predicted, gold), 6),
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
        "decision_regret": compute_decision_regret(chosen, best),
        "brier": round(compute_brier(preds, outcomes), 6) if preds else None,
        "ece": round(compute_ece(preds, outcomes), 6) if preds else None,
    }
