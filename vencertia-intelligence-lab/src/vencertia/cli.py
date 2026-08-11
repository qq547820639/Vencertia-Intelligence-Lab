from __future__ import annotations
import json
from pathlib import Path
import typer
from rich import print
from .domain import DecisionRequest, SolveRequest
from .runtime import DecisionRuntime
from .benchmark import BenchmarkRunner

app=typer.Typer(help='Vencertia Intelligence Lab')

@app.command()
def decide(path:Path):
    req=DecisionRequest.model_validate_json(path.read_text(encoding='utf-8'))
    result,apps=DecisionRuntime().decide(req)
    print(json.dumps({'result':result.model_dump(mode='json'),'evidence_applications':[a.model_dump(mode='json') for a in apps]},indent=2,ensure_ascii=False,default=str))

@app.command()
def benchmark(path:Path=Path('data/benchmarks/v0.2.jsonl')):
    report=BenchmarkRunner().run_file(path)
    print(json.dumps(report,indent=2,ensure_ascii=False))

@app.command()
def solve(path:Path):
    req=SolveRequest.model_validate_json(path.read_text(encoding='utf-8'))
    print(DecisionRuntime().solve(req).model_dump_json(indent=2))

@app.command()
def demo():
    p=Path(__file__).resolve().parents[2]/'examples'/'demo_saas_solve.json'
    req=SolveRequest.model_validate_json(p.read_text(encoding='utf-8'))
    print(DecisionRuntime().solve(req).model_dump_json(indent=2))


@app.command('validate-case')
def validate_case(path:Path):
    from .domain import HistoricalDecisionCase
    case=HistoricalDecisionCase.model_validate_json(path.read_text(encoding='utf-8'))
    print({'valid':True,'id':case.id,'leakage_audit_passed':case.leakage_audit_passed})

@app.command('prediction-add')
def prediction_add(path:Path, db:Path=Path('vencertia.db')):
    from .domain import PredictionRecord
    from .store import SQLiteStore
    p=PredictionRecord.model_validate_json(path.read_text(encoding='utf-8'))
    SQLiteStore(db).add_prediction(p); print({'saved':p.id,'db':str(db)})

@app.command('prediction-resolve')
def prediction_resolve(prediction_id:str, outcome:int, db:Path=Path('vencertia.db')):
    from .store import SQLiteStore
    if outcome not in (0,1): raise typer.BadParameter('outcome must be 0 or 1')
    p=SQLiteStore(db).resolve_prediction(prediction_id,outcome); print({'resolved':p.id,'outcome':p.outcome})

@app.command('calibration')
def calibration(db:Path=Path('vencertia.db')):
    from .store import SQLiteStore
    from .calibration import CalibrationEngine
    r=CalibrationEngine().report(SQLiteStore(db).predictions()); print(r.model_dump_json(indent=2))

if __name__=='__main__': app()
