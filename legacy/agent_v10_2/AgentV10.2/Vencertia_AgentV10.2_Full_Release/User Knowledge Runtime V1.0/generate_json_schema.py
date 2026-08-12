from pathlib import Path
import json

from runtime.models import (
    ContextBuildRequest,
    ContextBundle,
    MemoryCandidate,
    MemoryCandidateEnvelope,
    MemoryConflict,
    MemoryPermission,
    MemoryRecord,
    MemoryRetrievalQuery,
    MemoryWriteEvaluation,
    MemoryWriteRequest,
    MemoryWriteResult,
    UserKnowledgeProjection,
)

MODELS = [
    MemoryCandidate,
    MemoryCandidateEnvelope,
    MemoryRecord,
    MemoryPermission,
    MemoryConflict,
    MemoryWriteRequest,
    MemoryWriteResult,
    MemoryWriteEvaluation,
    MemoryRetrievalQuery,
    ContextBuildRequest,
    ContextBundle,
    UserKnowledgeProjection,
]

out = Path(__file__).parent / "json_schema"
out.mkdir(exist_ok=True)
index = {}
for model in MODELS:
    path = out / f"{model.__name__}.schema.json"
    path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index[model.__name__] = path.name
(out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"generated {len(MODELS)} schemas")
