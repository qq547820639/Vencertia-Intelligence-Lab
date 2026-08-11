from __future__ import annotations
import json
from pathlib import Path
from .domain import DecisionRequest, SolveRequest
from .runtime import DecisionRuntime

class BenchmarkRunner:
    def __init__(self): self.runtime=DecisionRuntime()
    def run_file(self,path:str|Path):
        rows=[]
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if not line.strip(): continue
            case=json.loads(line)
            req=DecisionRequest.model_validate(case['request'])
            solve=SolveRequest(decision=req,experiments=case.get('experiments',[]))
            solved=self.runtime.solve(solve)
            pred=solved.decision.recommended_option_id or 'NO_DECISION'
            gold=case['gold_option_id']
            exp_pred=solved.next_experiment.experiment.id if solved.next_experiment else None
            exp_gold=case.get('gold_experiment_id')
            rows.append({'id':case['id'],'predicted':pred,'gold':gold,'correct':pred==gold,
                         'experiment_predicted':exp_pred,'experiment_gold':exp_gold,
                         'experiment_correct': (exp_pred==exp_gold) if exp_gold is not None else True,
                         'status':solved.decision.status.value,'confidence':solved.decision.confidence,
                         'margin':solved.decision.decision_margin,'critical_belief':solved.decision.critical_belief_id})
        n=len(rows); decided=[r for r in rows if r['predicted']!='NO_DECISION']; exp=[r for r in rows if r['experiment_gold'] is not None]
        return {'n':n,
                'decision_accuracy':sum(r['correct'] for r in rows)/n if n else 0,
                'decision_coverage':len(decided)/n if n else 0,
                'selective_accuracy':sum(r['correct'] for r in decided)/len(decided) if decided else 0,
                'experiment_accuracy_on_abstentions':sum(r['experiment_correct'] for r in exp)/len(exp) if exp else None,
                'cases':rows}
