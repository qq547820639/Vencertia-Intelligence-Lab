import json
from pathlib import Path

from company_intelligence_runtime import (
    CaseContextPack, CaseUnitRef, ClaimTraceRequest, ClaimTraceResult,
    CompareCaseRequest, ComparisonResult, IngestCaseRequest, IngestCaseResult,
    SearchCasesRequest, SearchCasesResult, FounderRecord, FundingRound,
    GetCaseRequest, GetCaseResult, CompareCaseSetRequest, CompareCaseSetResult,
    ProposeCaseUpdateRequest, ProposeCaseUpdateResult, RefreshCaseRequest, RefreshCaseResult,
    SubmitEvidenceRequest, SubmitEvidenceResult, ResolveCaseConflictRequest, ResolveCaseConflictResult,
)

MODELS = [
    CaseUnitRef, FounderRecord, FundingRound,
    IngestCaseRequest, IngestCaseResult, SearchCasesRequest, SearchCasesResult,
    CompareCaseRequest, ComparisonResult, CaseContextPack, ClaimTraceRequest, ClaimTraceResult,
    GetCaseRequest, GetCaseResult, CompareCaseSetRequest, CompareCaseSetResult,
    ProposeCaseUpdateRequest, ProposeCaseUpdateResult, RefreshCaseRequest, RefreshCaseResult,
    SubmitEvidenceRequest, SubmitEvidenceResult, ResolveCaseConflictRequest, ResolveCaseConflictResult,
]

out = Path(__file__).with_name("json_schema")
out.mkdir(exist_ok=True)
index = {}
for model in MODELS:
    path = out / f"{model.__name__}.schema.json"
    path.write_text(json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False), encoding="utf-8")
    index[model.__name__] = path.name
(out / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"generated {len(MODELS)} schemas in {out}")
