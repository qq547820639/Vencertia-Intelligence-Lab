from __future__ import annotations
from .domain import DecisionRequest, DecisionResult, DecisionStatus, Experiment, RankedExperiment, SolveRequest, SolveResult
from .evidence import EvidenceEngine
from .decision import DecisionEngine
from .experiments import ExperimentOptimizer

class DecisionRuntime:
    """One deterministic iteration of the Vencertia loop."""
    def __init__(self):
        self.evidence_engine=EvidenceEngine(); self.decision_engine=DecisionEngine(); self.experiment_optimizer=ExperimentOptimizer()

    def decide(self, req: DecisionRequest) -> tuple[DecisionResult, list]:
        beliefs, applications=self.evidence_engine.apply(req.beliefs, req.evidence)
        result=self.decision_engine.evaluate(req.id,req.options,beliefs,req.risk_aversion,
            req.minimum_decision_margin,req.max_unresolved_critical_uncertainty)
        return result, applications

    def solve(self, req: SolveRequest) -> SolveResult:
        result, applications = self.decide(req.decision)
        nxt = None
        if result.status == DecisionStatus.INSUFFICIENT_EVIDENCE and req.experiments:
            nxt = self.next_experiment(req.decision, req.experiments, result.critical_belief_id)
            if nxt:
                result.reversible_next_step = nxt.experiment.name
        return SolveResult(decision=result, next_experiment=nxt, evidence_applications=applications)

    def next_experiment(self, req: DecisionRequest, experiments: list[Experiment], critical_belief_id: str | None = None) -> RankedExperiment | None:
        beliefs,_=self.evidence_engine.apply(req.beliefs,req.evidence)
        ranked=self.experiment_optimizer.rank(experiments,beliefs,critical_belief_id)
        return ranked[0] if ranked else None
