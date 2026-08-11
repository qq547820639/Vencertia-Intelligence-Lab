from fastapi import FastAPI
from pydantic import BaseModel
from .domain import DecisionRequest, Experiment, SolveRequest
from .runtime import DecisionRuntime

app=FastAPI(title='Vencertia Decision Runtime',version='0.1.0')
runtime=DecisionRuntime()

class DecideResponse(BaseModel):
    result: dict
    evidence_applications: list[dict]

@app.get('/health')
def health(): return {'ok':True,'version':'0.1.0'}

@app.post('/v1/decide')
def decide(req:DecisionRequest):
    result,apps=runtime.decide(req)
    return {'result':result.model_dump(mode='json'),'evidence_applications':[a.model_dump(mode='json') for a in apps]}

class ExperimentRequest(BaseModel):
    decision: DecisionRequest
    experiments: list[Experiment]

@app.post('/v1/next-experiment')
def next_experiment(req:ExperimentRequest):
    x=runtime.next_experiment(req.decision,req.experiments)
    return x.model_dump(mode='json') if x else None

@app.post('/v1/solve')
def solve(req:SolveRequest):
    return runtime.solve(req).model_dump(mode='json')
