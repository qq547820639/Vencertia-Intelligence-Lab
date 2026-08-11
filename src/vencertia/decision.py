from __future__ import annotations
from .domain import Belief, DecisionOption, DecisionResult, DecisionStatus, OptionScore

class DecisionEngine:
    def evaluate(self, decision_id: str, options: list[DecisionOption], beliefs: list[Belief],
                 risk_aversion: float=0.25, minimum_margin: float=0.08,
                 max_critical_uncertainty: float=0.45) -> DecisionResult:
        bm={b.id:b for b in beliefs}
        scores=[]
        # Expected utility under current beliefs, with uncertainty and irreversible/opportunity-cost penalties.
        for o in options:
            eu=o.base_utility + sum(c*bm[k].probability for k,c in o.belief_coefficients.items())
            uncertainty=sum(abs(c)*bm[k].uncertainty for k,c in o.belief_coefficients.items())
            penalty=risk_aversion*uncertainty + o.irreversible_cost + o.opportunity_cost
            scores.append(OptionScore(option_id=o.id, expected_utility=eu,
                                      uncertainty_penalty=penalty, adjusted_utility=eu-penalty))
        scores.sort(key=lambda x:x.adjusted_utility, reverse=True)
        best, second=scores[0],scores[1]
        margin=best.adjusted_utility-second.adjusted_utility

        # Decision-critical uncertainty = weighted uncertainty among beliefs whose coefficients differ most across top options.
        bo=next(o for o in options if o.id==best.option_id); so=next(o for o in options if o.id==second.option_id)
        impacts=[]
        for bid,b in bm.items():
            delta=abs(bo.belief_coefficients.get(bid,0)-so.belief_coefficients.get(bid,0))
            impacts.append((delta*b.uncertainty, bid, b.uncertainty, delta))
        impacts.sort(reverse=True)
        _,critical_id,critical_uncertainty,_ = impacts[0] if impacts else (0,None,0,0)

        conf = max(0.0,min(1.0, 0.5 + 0.35*min(1.0,abs(margin)) - 0.35*critical_uncertainty))
        rationale=[
            f"Top option {best.option_id} adjusted utility={best.adjusted_utility:.3f}; runner-up={second.adjusted_utility:.3f}.",
            f"Decision margin={margin:.3f}; critical uncertainty={critical_uncertainty:.3f} ({critical_id}).",
        ]
        if margin < minimum_margin or critical_uncertainty > max_critical_uncertainty:
            status=DecisionStatus.INSUFFICIENT_EVIDENCE
            rec=None
            rationale.append("Decision has not converged; acquire decision-changing evidence before committing.")
        else:
            rec=best.option_id
            label=best.option_id.lower()
            if 'kill' in label or 'stop' in label: status=DecisionStatus.KILL
            elif 'pivot' in label: status=DecisionStatus.PIVOT
            elif 'hold' in label or 'wait' in label: status=DecisionStatus.HOLD
            else: status=DecisionStatus.GO
            rationale.append("Decision converged under current policy thresholds; prefer reversible execution where possible.")
        return DecisionResult(decision_id=decision_id,status=status,recommended_option_id=rec,
            confidence=conf,decision_margin=margin,option_scores=scores,critical_belief_id=critical_id,
            critical_uncertainty=critical_uncertainty,rationale=rationale)
