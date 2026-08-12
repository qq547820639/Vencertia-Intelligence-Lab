"""ResearchStopRule — signal-based research stopping (ADR-011).

Evaluates 8 classes of signals after each research round and returns one of:
RESEARCH_MORE / SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED. When desktop research
can no longer move beliefs, the rule honestly declares SEARCH_EXHAUSTED; when
only real-world observation can resolve the remaining uncertainty, it returns
EXPERIMENT_REQUIRED.

v1.1.2 (P1-8): all signals are REAL:
- ``belief_delta``: target-only posterior delta (from ``RoundSummary``)
- ``source_quality``: mean applied-evidence authority × verification
  (EvidencePolicy tables; 0.0 when no applied evidence — never a fake 0.5)
- ``claim_coverage``: claim-based coverage of target claims (never an
  evidence-id string guess)
- ``decision_sensitivity_signal``: recommendation flip → 1.0, else
  distance-to-flip reduction ratio (no statistical claim → not "probability")
- ``decision_change_prob`` kept as a DEPRECATED alias
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    Evidence,
    ResearchStopReport,
    ResearchTrace,
)
from vencertia.runtime.evidence_policy import AUTHORITY_TABLE, VERIFICATION_MULTIPLIER


@dataclass
class RoundSummary:
    """Per-round evidence needed for real stop signals (P1-8)."""

    applied_evidence: list[Evidence] = field(default_factory=list)
    bindings: list = field(default_factory=list)  # evidence→claim bindings
    target_claim_ids: list[str] = field(default_factory=list)
    beliefs_before: list[Belief] = field(default_factory=list)
    beliefs_after: list[Belief] = field(default_factory=list)
    decision_before: Decision | None = None
    decision_result_before: Any | None = None
    decision_result_after: Any | None = None
    queries_executed: int = 0
    latency_ms: float = 0.0


class ResearchStopRule:
    """Deterministic stopping rule over research traces + belief deltas."""

    def __init__(
        self,
        settings: Settings | None = None,
        sensitivity=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sensitivity = sensitivity

    def evaluate(
        self,
        traces: list[ResearchTrace],
        beliefs_before: list[Belief],
        beliefs_after: list[Belief],
        target_claims: list[str],
        decision: Decision | None = None,
        round_no: int = 1,
        round_summary: RoundSummary | None = None,
    ) -> ResearchStopReport:
        summary = round_summary

        # 1) belief_delta — target-only posterior delta.
        target_ids = (
            set(summary.target_claim_ids)
            if summary is not None and summary.target_claim_ids
            else set(target_claims)
        )
        before = {b.claim_id: b.probability for b in beliefs_before}
        after = {b.claim_id: b.probability for b in beliefs_after}
        relevant = target_ids or (set(before) | set(after))
        deltas = [
            abs(after.get(cid, before.get(cid, 0.5)) - before.get(cid, 0.5))
            for cid in relevant
            if cid in before or cid in after
        ]
        avg_delta = round(sum(deltas) / len(deltas), 6) if deltas else 0.0

        # 2) duplicate rate (kept from traces).
        retrieved = sum(t.results_retrieved for t in traces)
        dropped = sum(t.duplicate_dropped for t in traces)
        duplicate_rate = round(dropped / retrieved, 6) if retrieved else 0.0

        # 3) claim_coverage — claim-based (P1-8): bound target claims /
        #    requested target claims. Evidence ids are NEVER used as claim ids.
        claim_coverage = 0.0
        if summary is not None:
            bound_target: set[str] = set()
            for binding in summary.bindings:
                cid = getattr(binding, "claim_id", None)
                if cid and cid in summary.target_claim_ids:
                    bound_target.add(cid)
            for ev in summary.applied_evidence:
                for cid in (ev.claim_ids or []):
                    if cid in summary.target_claim_ids:
                        bound_target.add(cid)
            claim_coverage = round(
                len(bound_target) / max(1, len(summary.target_claim_ids)), 6
            )

        # 4) source_quality — real authority × verification mean (P1-8).
        #    No applied evidence → 0.0 (never the old fake 0.5).
        source_quality = 0.0
        if summary is not None and summary.applied_evidence:
            weights: list[float] = []
            for ev in summary.applied_evidence:
                key = (
                    ev.authority_level.value
                    if hasattr(ev.authority_level, "value")
                    else str(ev.authority_level)
                )
                vkey = (
                    ev.verification.value
                    if hasattr(ev.verification, "value")
                    else str(ev.verification)
                )
                weights.append(
                    AUTHORITY_TABLE.get(key, 0.1)
                    * VERIFICATION_MULTIPLIER.get(vkey, 0.2)
                )
            source_quality = round(sum(weights) / len(weights), 6)

        queries_executed = sum(t.queries_executed for t in traces)
        latest_round_new = len(traces[-1].new_evidence_ids) if traces else 0
        source_diversity = round(
            min(1.0, max(0, len({t.provider for t in traces if t.provider})) / 3.0), 6
        )

        # 5) decision_sensitivity_signal (P1-8) — replaces the misleading
        #    "decision_change_prob = avg_delta". Recommendation flip → 1.0;
        #    else distance-to-flip reduction ratio. No statistical basis, so
        #    it is NOT called a probability.
        decision_sensitivity_signal = 0.0
        if (
            summary is not None
            and summary.decision_result_before is not None
            and summary.decision_result_after is not None
        ):
            rec_before = getattr(summary.decision_result_before, "recommended_option_id", None)
            rec_after = getattr(summary.decision_result_after, "recommended_option_id", None)
            if rec_before != rec_after:
                decision_sensitivity_signal = 1.0
            else:
                margin_before = getattr(
                    summary.decision_result_before, "decision_margin", None
                )
                margin_after = getattr(summary.decision_result_after, "decision_margin", None)
                if (
                    isinstance(margin_before, (int, float))
                    and isinstance(margin_after, (int, float))
                    and margin_before > 0
                ):
                    decision_sensitivity_signal = round(
                        max(0.0, min(1.0, 1.0 - margin_after / margin_before)), 6
                    )
        # Deprecated alias (kept for backward compatibility; do not use in new
        # decision logic).
        decision_change_prob = decision_sensitivity_signal

        # 6) search_cost — real queries + latency.
        latency_ms = round(summary.latency_ms, 3) if summary is not None else 0.0
        search_cost = {
            "queries_executed": queries_executed,
            "latency_ms": latency_ms,
        }

        signals = {
            "marginal_value": avg_delta,
            "belief_delta": avg_delta,
            "duplicate_rate": duplicate_rate,
            "source_quality": source_quality,
            "source_diversity": source_diversity,
            "claim_coverage": claim_coverage,
            "search_cost": search_cost,
            "decision_sensitivity_signal": decision_sensitivity_signal,
            "decision_change_prob": decision_change_prob,
        }

        if round_no >= self.settings.research_max_rounds:
            return ResearchStopReport(
                status="SEARCH_EXHAUSTED",
                reason=f"Reached max research rounds ({round_no}/{self.settings.research_max_rounds}).",
                signals=signals,
            )

        if (
            avg_delta < self.settings.research_stop_marginal_value
            and duplicate_rate > self.settings.research_stop_duplicate_rate
            and round_no > 1
        ):
            return ResearchStopReport(
                status="SEARCH_EXHAUSTED",
                reason=(
                    f"Marginal belief delta ({avg_delta}) below "
                    f"{self.settings.research_stop_marginal_value} with duplicate rate "
                    f"{duplicate_rate} above {self.settings.research_stop_duplicate_rate}."
                ),
                signals=signals,
            )

        if round_no > 1 and latest_round_new == 0 and retrieved > 0:
            return ResearchStopReport(
                status="EXPERIMENT_REQUIRED",
                reason="Desktop research returned no new unique evidence; a real-world experiment is required.",
                signals=signals,
            )

        return ResearchStopReport(
            status="RESEARCH_MORE",
            reason="Marginal evidence value above threshold; continue research.",
            signals=signals,
        )
