from pathlib import Path
from vencertia.domain import DecisionRequest
from vencertia.runtime import DecisionRuntime

def test_demo_runs():
    root=Path(__file__).resolve().parents[1]
    req=DecisionRequest.model_validate_json((root/'examples/demo_saas.json').read_text())
    result,apps=DecisionRuntime().decide(req)
    assert result.option_scores and len(apps)==2
    assert result.critical_belief_id is not None
