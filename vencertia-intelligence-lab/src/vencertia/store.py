from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .domain import PredictionRecord

SCHEMA='''
CREATE TABLE IF NOT EXISTS objects(type TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(type,id));
CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
'''

class SQLiteStore:
    def __init__(self,path: str|Path='vencertia.db'):
        self.path=str(path); self.db=sqlite3.connect(self.path); self.db.executescript(SCHEMA)
    def put(self,typ:str,obj):
        oid=getattr(obj,'id'); payload=obj.model_dump_json()
        self.db.execute("INSERT OR REPLACE INTO objects(type,id,payload,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",(typ,oid,payload)); self.db.commit()
    def add_prediction(self,p:PredictionRecord):
        self.db.execute("INSERT OR REPLACE INTO predictions(id,payload,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",(p.id,p.model_dump_json())); self.db.commit()
    def resolve_prediction(self,prediction_id:str,outcome:int,resolved_at=None):
        from datetime import datetime, timezone
        row=self.db.execute("SELECT payload FROM predictions WHERE id=?",(prediction_id,)).fetchone()
        if not row: raise KeyError(prediction_id)
        p=PredictionRecord.model_validate_json(row[0])
        p.outcome=int(outcome); p.resolved_at=resolved_at or datetime.now(timezone.utc)
        self.add_prediction(p); return p
    def predictions(self)->list[PredictionRecord]:
        return [PredictionRecord.model_validate_json(r[0]) for r in self.db.execute("SELECT payload FROM predictions ORDER BY id")]
