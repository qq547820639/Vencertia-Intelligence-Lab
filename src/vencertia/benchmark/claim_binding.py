"""ClaimBindingBenchmarkRunner — deterministic synthetic benchmark (GAP-04).

**This is a SYNTHETIC Claim Binding Benchmark.** It is constructed from
hand-crafted cases that exercise the deterministic ClaimBindingEngine paths.
The reported numbers measure the engine against these synthetic cases only;
they are NOT real-world accuracy on live search data. Do not present any
metric here as production accuracy.

Each case carries:
  - ``id`` / ``category`` (one of the 14 GAP-04 categories)
  - ``evidence``: {id, scope, source}
  - ``claims``: [{id, statement, scope}]
  - ``gold_status``: BOUND | AMBIGUOUS | REJECTED | UNBOUND_EVIDENCE
  - ``gold_claim_ids``: expected bound claim ids (BOUND cases)
  - ``gold_candidate_claim_ids``: optional for AMBIGUOUS (a set of close
    candidates; a unique answer is not forced)
  - ``config``: optional per-case overrides (binding_confidence_threshold,
    binding_ambiguity_margin, binding_min_score, binding_reject_threshold)

Metrics (8 + Coverage):
  Precision / Recall / F1 (claim-level, BOUND judgments)
  Unbound Accuracy / Ambiguous Accuracy / Rejected Accuracy (status-level)
  Multi-Claim Exact Match / Multi-Claim Partial Match (BOUND multi-claim)
  Coverage (cases that produced a judgment / total)

Division by zero is guarded: a metric with a zero denominator is reported as
``None`` and rendered as ``N/A`` (never faked as 0.0).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vencertia.config import Settings, get_settings
from vencertia.domain import Claim, ClaimBindingInput, Scope
from vencertia.runtime.claim_binding import (
    ClaimBindingEngine,
    ClaimExtractor,
    DeterministicClaimMatcher,
    EvidenceClaimLinker,
)
from vencertia.runtime.evidence_policy import EvidencePolicy

CATEGORIES = (
    "single_match",
    "multi_claim",
    "irrelevant",
    "ambiguous",
    "rejected_scope",
    "company_case",
    "project_outcome",
    "external_research",
    "llm_inference",
    "contradiction",
    "near_duplicate_claims",
    "same_keywords_different_meaning",
    "weak_lexical_overlap",
    "strong_semantic_relation",
)

METRIC_NAMES = (
    "precision",
    "recall",
    "f1",
    "unbound_accuracy",
    "ambiguous_accuracy",
    "rejected_accuracy",
    "multi_claim_exact_match",
    "multi_claim_partial_match",
    "coverage",
)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    """Return numerator/denominator or None (N/A) when denominator is zero."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _scope(value: str) -> Scope:
    # v1.9: fail loud on an unknown scope — silently mapping typos to MARKET
    # hid authored-case errors behind a plausible-but-wrong scope.
    try:
        return Scope(value)
    except ValueError as exc:
        raise ValueError(f"unknown scope {value!r} in claim-binding case") from exc


@dataclass
class ClaimBindingCaseResult:
    """Per-case prediction (also used for auditing and docs)."""

    id: str
    category: str
    gold_status: str
    predicted_status: str
    gold_claim_ids: list[str] = field(default_factory=list)
    predicted_claim_ids: list[str] = field(default_factory=list)
    gold_candidate_claim_ids: list[str] = field(default_factory=list)
    correct: bool = False
    known_limitation: bool = False
    reason: str = ""


@dataclass
class ClaimBindingBenchmarkReport:
    """Full benchmark report (metrics + per-case audit trail)."""

    level: str = "CLAIM_BINDING"
    source: str = ""
    n: int = 0
    metrics: dict[str, float | None] = field(default_factory=dict)
    cases: list[ClaimBindingCaseResult] = field(default_factory=list)
    synthetic: bool = True


class ClaimBindingBenchmarkRunner:
    """Runs the deterministic ClaimBindingEngine over synthetic cases."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _engine(self, config: dict[str, Any]) -> ClaimBindingEngine:
        settings = Settings(**{**dataclasses.asdict(self.settings), **config})
        return ClaimBindingEngine(
            extractor=ClaimExtractor(settings=settings),
            matcher=DeterministicClaimMatcher(settings),
            linker=EvidenceClaimLinker(),
            policy=EvidencePolicy(settings),
            settings=settings,
        )

    def _run_case(self, raw: dict[str, Any]) -> ClaimBindingCaseResult:
        case_id = str(raw.get("id", "?"))
        category = str(raw.get("category", "single_match"))
        gold_status = str(raw.get("gold_status", "BOUND"))
        gold_claim_ids = list(raw.get("gold_claim_ids") or [])
        gold_candidates = list(raw.get("gold_candidate_claim_ids") or [])
        config = dict(raw.get("config") or {})

        evidence_raw = dict(raw.get("evidence") or {})
        claims_raw = list(raw.get("claims") or [])
        claims = [
            Claim(
                id=str(c["id"]),
                statement=str(c["statement"]),
                scope=_scope(str(c.get("scope", "PROJECT"))),
            )
            for c in claims_raw
        ]

        engine = self._engine(config)
        output = engine.process(
            ClaimBindingInput(
                research_results=[
                    {
                        "id": str(evidence_raw.get("id", f"E_{case_id}")),
                        "source": str(evidence_raw.get("source", "")),
                        "scope": str(evidence_raw.get("scope", "MARKET")),
                    }
                ],
                context={"claims": claims},
                existing_claims=claims,
                auto_extract=True,
                binding_confidence_threshold=float(
                    config.get("binding_confidence_threshold", self.settings.binding_confidence_threshold)
                ),
                binding_min_score=config.get("binding_min_score"),
                binding_ambiguity_margin=config.get("binding_ambiguity_margin"),
                binding_reject_threshold=config.get("binding_reject_threshold"),
            )
        )

        if output.bindings:
            predicted_status = "BOUND"
            predicted_ids = sorted({b.claim_id for b in output.bindings if b.claim_id})
        elif output.unbound:
            predicted_status = output.unbound[0].status
            predicted_ids = []
        else:
            predicted_status = "UNBOUND_EVIDENCE"
            predicted_ids = []

        # Correctness: status must match gold.
        correct = predicted_status == gold_status
        reason = ""
        if gold_status == "BOUND" and predicted_status == "BOUND":
            gold_set = set(gold_claim_ids)
            pred_set = set(predicted_ids)
            correct = gold_set == pred_set
            if not correct:
                reason = f"gold={sorted(gold_set)} predicted={sorted(pred_set)}"
        elif gold_status == "AMBIGUOUS" and predicted_status == "AMBIGUOUS":
            if gold_candidates:
                # A unique answer is NOT forced: any non-empty overlap with the
                # candidate set is acceptable.
                correct = bool(set(gold_candidates) & set(output.unbound[0].candidate_claim_ids))
                if not correct:
                    reason = (
                        "candidates "
                        f"{sorted(output.unbound[0].candidate_claim_ids)} do not overlap "
                        f"gold candidates {sorted(gold_candidates)}"
                    )
        elif predicted_status != gold_status:
            reason = f"expected {gold_status}, got {predicted_status}"

        return ClaimBindingCaseResult(
            id=case_id,
            category=category,
            gold_status=gold_status,
            predicted_status=predicted_status,
            gold_claim_ids=gold_claim_ids,
            predicted_claim_ids=predicted_ids,
            gold_candidate_claim_ids=gold_candidates,
            correct=correct,
            known_limitation=bool(raw.get("known_limitation", False)),
            reason=reason,
        )

    def run(self, path: str | Path) -> ClaimBindingBenchmarkReport:
        path = Path(path)
        raw_cases = json.loads(path.read_text(encoding="utf-8"))
        results = [self._run_case(raw) for raw in raw_cases]
        return self._aggregate(results, str(path))

    def run_cases(self, raw_cases: list[dict]) -> ClaimBindingBenchmarkReport:
        results = [self._run_case(raw) for raw in raw_cases]
        return self._aggregate(results, "<inline>")

    def _aggregate(
        self, results: list[ClaimBindingCaseResult], source: str
    ) -> ClaimBindingBenchmarkReport:
        n = len(results)
        judged = [r for r in results if r.predicted_status in (
            "BOUND", "AMBIGUOUS", "REJECTED", "UNBOUND_EVIDENCE"
        )]

        # --- claim-level Precision / Recall / F1 (BOUND judgments) -----------
        tp = fp = fn = 0
        for r in results:
            gold = set(r.gold_claim_ids)
            pred = set(r.predicted_claim_ids)
            tp += len(gold & pred)
            fp += len(pred - gold)
            fn += len(gold - pred)
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        f1 = (
            round(2 * precision * recall / (precision + recall), 6)
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )

        # --- status-level accuracies -----------------------------------------
        def _status_accuracy(status: str) -> float | None:
            gold_cases = [r for r in results if r.gold_status == status]
            if not gold_cases:
                return None
            hits = sum(1 for r in gold_cases if r.predicted_status == status and r.correct)
            return _safe_ratio(hits, len(gold_cases))

        # --- multi-claim exact / partial match (BOUND gold with >=2 ids) -----
        multi = [r for r in results if r.gold_status == "BOUND" and len(r.gold_claim_ids) >= 2]
        exact = partial = 0
        for r in multi:
            gold_set = set(r.gold_claim_ids)
            pred_set = set(r.predicted_claim_ids)
            inter = gold_set & pred_set
            if pred_set == gold_set:
                exact += 1
            elif inter:
                partial += 1

        metrics: dict[str, float | None] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "unbound_accuracy": _status_accuracy("UNBOUND_EVIDENCE"),
            "ambiguous_accuracy": _status_accuracy("AMBIGUOUS"),
            "rejected_accuracy": _status_accuracy("REJECTED"),
            "multi_claim_exact_match": _safe_ratio(exact, len(multi)),
            "multi_claim_partial_match": _safe_ratio(partial, len(multi)),
            "coverage": _safe_ratio(len(judged), n),
        }
        return ClaimBindingBenchmarkReport(
            level="CLAIM_BINDING",
            source=source,
            n=n,
            metrics=metrics,
            cases=results,
            synthetic=True,
        )

    @staticmethod
    def render(report: ClaimBindingBenchmarkReport) -> str:
        """Human-readable report (N/A for zero-denominator metrics)."""
        lines = [
            "Synthetic Claim Binding Benchmark (NOT real-world accuracy)",
            f"source   : {report.source}",
            f"cases    : {report.n}",
            f"coverage : {report.metrics.get('coverage')}",
            "",
            "metrics:",
        ]
        for name in METRIC_NAMES:
            value = report.metrics.get(name)
            rendered = "N/A" if value is None else f"{value:.6f}"
            lines.append(f"  {name:<28} {rendered}")
        lines.append("")
        lines.append("per-case:")
        for r in report.cases:
            mark = "PASS" if r.correct else ("KNOWN-LIMIT" if r.known_limitation else "FAIL")
            detail = (
                f"gold={r.gold_status} pred={r.predicted_status}"
                + (f" reason={r.reason}" if r.reason else "")
            )
            lines.append(f"  [{mark}] {r.id:<12} {r.category:<32} {detail}")
        return "\n".join(lines)


__all__ = [
    "CATEGORIES",
    "METRIC_NAMES",
    "ClaimBindingBenchmarkReport",
    "ClaimBindingBenchmarkRunner",
    "ClaimBindingCaseResult",
]
