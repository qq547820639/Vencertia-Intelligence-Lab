from datetime import datetime,timezone,timedelta
from vencertia.domain import PredictionRecord
from vencertia.calibration import CalibrationEngine

def test_perfectish_calibration_report():
    now=datetime.now(timezone.utc)
    rows=[PredictionRecord(id=str(i),target='x',probability=p,due_at=now,outcome=o) for i,(p,o) in enumerate([(0.9,1),(0.8,1),(0.2,0),(0.1,0)])]
    r=CalibrationEngine().report(rows,5)
    assert r.n==4 and r.brier_score < 0.05
