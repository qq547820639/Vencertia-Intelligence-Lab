from datetime import datetime, timezone
from vencertia.domain import PredictionRecord
from vencertia.store import SQLiteStore
from vencertia.calibration import CalibrationEngine

def test_prediction_roundtrip(tmp_path):
    db=SQLiteStore(tmp_path/'x.db')
    p=PredictionRecord(id='p1',target='paid pilot',probability=.7,due_at=datetime.now(timezone.utc))
    db.add_prediction(p); db.resolve_prediction('p1',1)
    rows=db.predictions()
    assert rows[0].outcome==1
    assert CalibrationEngine().report(rows).n==1
