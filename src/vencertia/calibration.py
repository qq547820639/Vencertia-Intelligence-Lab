from __future__ import annotations
from .domain import PredictionRecord, CalibrationReport

class CalibrationEngine:
    def report(self, rows: list[PredictionRecord], bins: int=10) -> CalibrationReport:
        done=[r for r in rows if r.outcome is not None]
        if not done:
            return CalibrationReport(n=0,brier_score=None,expected_calibration_error=None,
                                     mean_confidence=None,empirical_rate=None,bins=[])
        n=len(done)
        brier=sum((r.probability-r.outcome)**2 for r in done)/n
        out=[]; ece=0.0
        for i in range(bins):
            lo=i/bins; hi=(i+1)/bins
            bucket=[r for r in done if lo <= r.probability < hi or (i==bins-1 and r.probability==1)]
            if not bucket: continue
            conf=sum(r.probability for r in bucket)/len(bucket)
            rate=sum(r.outcome for r in bucket)/len(bucket)
            ece += (len(bucket)/n)*abs(conf-rate)
            out.append({'lo':lo,'hi':hi,'n':len(bucket),'mean_confidence':conf,'empirical_rate':rate,'gap':conf-rate})
        return CalibrationReport(n=n,brier_score=brier,expected_calibration_error=ece,
            mean_confidence=sum(r.probability for r in done)/n,
            empirical_rate=sum(r.outcome for r in done)/n,bins=out)
