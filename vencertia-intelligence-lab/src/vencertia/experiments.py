from __future__ import annotations
from .domain import Belief, Experiment, RankedExperiment

class ExperimentOptimizer:
    def rank(self, experiments: list[Experiment], beliefs: list[Belief], critical_belief_id: str | None = None) -> list[RankedExperiment]:
        bm={b.id:b for b in beliefs}
        ranked=[]
        for e in experiments:
            target_uncertainty=sum(bm[x].uncertainty*bm[x].decision_weight for x in e.target_belief_ids if x in bm)
            # Information value / cost / time, favor reversible actions. Log-like time penalty avoids overpunishing 2-3 day tests.
            denom=e.cost * (1.0 + 0.15*max(0,e.days-1))
            critical_boost = 2.0 if critical_belief_id and critical_belief_id in e.target_belief_ids else 1.0
            score=(e.expected_information_gain * e.decision_impact * max(0.05,target_uncertainty) *
                   (0.5+0.5*e.reversibility) * critical_boost)/denom
            ranked.append(RankedExperiment(experiment=e,priority_score=score))
        return sorted(ranked,key=lambda x:x.priority_score,reverse=True)
