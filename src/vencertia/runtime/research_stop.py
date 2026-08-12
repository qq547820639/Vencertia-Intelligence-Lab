"""ResearchStopRule — signal-based research stopping (ADR-011).

Evaluates 8 classes of signals after each research round and returns one of:
RESEARCH_MORE / SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED. When desktop research
can no longer move beliefs, the rule honestly declares SEARCH_EXHAUSTED; when
only real-world observation can resolve the remaining uncertainty, it returns
EXPERIMENT_REQUIRED.
"""

from __future__ import annotations

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    ResearchStopReport,
    ResearchTrace,
)


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
    ) -> ResearchStopReport:
        before = {b.id: b.probability for b in beliefs_before}
        after = {b.id: b.probability for b in beliefs_after}
        all_ids = set(before) | set(after)
        deltas = [abs(after.get(bid, before.get(bid, 0.5)) - before.get(bid, 0.5)) for bid in all_ids]
        avg_delta = round(sum(deltas) / len(deltas), 6) if deltas else 0.0

        retrieved = sum(t.results_retrieved for t in traces)
        dropped = sum(t.duplicate_dropped for t in traces)
        duplicate_rate = round(dropped / retrieved, 6) if retrieved else 0.0

        queries_executed = sum(t.queries_executed for t in traces)
        new_evidence = [eid for t in traces for eid in t.new_evidence_ids]
        covered = len({eid.split(":")[0] for eid in new_evidence})
        claim_coverage = round(covered / max(1, len(target_claims)), 6)

        # Source quality: average authority weight of applied evidence per trace
        # is approximated from trace metadata (provider/model only), so we keep
        # a neutral 0.5 when no per-evidence authority is available.
        # [H2] upgrade path: pass applied-evidence authorities into the stop
        # rule (or read from the repo) to compute a real per-round mean.
        source_quality = 0.5
        latest_round_new = len(traces[-1].new_evidence_ids) if traces else 0
        source_diversity = round(min(1.0, max(0, len({t.provider for t in traces if t.provider})) / 3.0), 6)
        decision_change_prob = round(avg_delta, 6)

        signals = {
            "marginal_value": avg_delta,
            "belief_delta": avg_delta,
            "duplicate_rate": duplicate_rate,
            "source_quality": source_quality,
            "source_diversity": source_diversity,
            "claim_coverage": claim_coverage,
            "search_cost": queries_executed,
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
