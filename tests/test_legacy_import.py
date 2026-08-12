"""Legacy V10.2 mapping + importer tests."""

from __future__ import annotations

from pathlib import Path

from vencertia.legacy.import_v10_2 import (
    V10_2Importer,
    build_mapping_dictionary,
    extract_v10_2_enums,
)
from vencertia.legacy.mapping import (
    MAPPING_VERSION,
    map_company_case,
    map_memory_record,
    map_rules,
)
from vencertia.repositories.memory import InMemoryRepository


def test_map_memory_record():
    record = {
        "memory_id": "M_1",
        "user_id": "u1",
        "project_id": None,
        "scope": "USER_GLOBAL",
        "memory_type": "CONSTRAINT",
        "content": "10 hours per week",
        "structured_value": {"hours_per_week": 10},
        "fact_status": "VERIFIED",
        "confidence": "HIGH",
        "importance": "CRITICAL",
        "status": "ACTIVE",
    }
    mapped = map_memory_record(record)
    assert mapped.memory_id == "M_1"
    assert mapped.scope == "USER_GLOBAL"
    assert mapped.memory_type == "CONSTRAINT"
    assert mapped.fact_status == "VERIFIED"
    assert mapped.id == "M_1"


def test_map_company_case():
    data = {"company_id": "CMP_HUB", "canonical_name": "HubSpot", "case_roles": ["SUCCESS"]}
    case = map_company_case(data)
    assert case.company_id == "CMP_HUB"
    assert case.canonical_name == "HubSpot"


def test_map_rules_includes_invariants():
    rules = map_rules()
    kinds = {r.kind for r in rules}
    assert "INVARIANT" in kinds
    assert "POLICY" in kinds
    assert "HEURISTIC" in kinds
    names = {r.name for r in rules}
    assert "killed_not_primary" in names
    assert "transferability_requires_review" in names
    assert "funding_not_demand_evidence" in names


def test_extract_v10_2_enums(project_root: Path):
    models_py = (
        project_root
        / "legacy"
        / "agent_v10_2"
        / "AgentV10.2"
        / "Vencertia_AgentV10.2_Full_Release"
        / "User Knowledge Runtime V1.0"
        / "runtime"
        / "models.py"
    )
    if not models_py.exists():
        return  # environment without the release; skip silently
    enums = extract_v10_2_enums(models_py)
    assert "MemoryScope" in enums
    assert "MemoryType" in enums
    assert len(enums["MemoryType"]) >= 20
    assert "USER_GLOBAL" in enums["MemoryScope"]


def test_build_mapping_dictionary(project_root: Path):
    models_py = (
        project_root
        / "legacy"
        / "agent_v10_2"
        / "AgentV10.2"
        / "Vencertia_AgentV10.2_Full_Release"
        / "User Knowledge Runtime V1.0"
        / "runtime"
        / "models.py"
    )
    if not models_py.exists():
        return
    mapping = build_mapping_dictionary(models_py)
    assert mapping["mapping_version"] == MAPPING_VERSION
    assert mapping["source_type_to_authority"]["REAL_PAYMENT"] == "PROJECT_REALITY"


def test_importer_dry_run_and_import(project_root: Path):
    source = (
        project_root
        / "legacy"
        / "agent_v10_2"
        / "AgentV10.2"
        / "Vencertia_AgentV10.2_Full_Release"
    )
    if not source.exists():
        return
    repo = InMemoryRepository()
    importer = V10_2Importer(source_dir=source, repo=repo)
    dry = importer.dry_run()
    assert dry.manifest.total > 0
    assert dry.coverage > 0.5

    first = importer.import_all()
    assert first.imported > 0
    # Idempotency: second import adds nothing new.
    second = importer.import_all()
    assert second.imported == 0
    assert second.skipped_duplicates >= first.imported


def test_importer_memory_import(project_root: Path):
    source = (
        project_root
        / "legacy"
        / "agent_v10_2"
        / "AgentV10.2"
        / "Vencertia_AgentV10.2_Full_Release"
    )
    if not source.exists():
        return
    repo = InMemoryRepository()
    importer = V10_2Importer(source_dir=source, repo=repo)
    report = importer.import_memory()
    # The release ships a memory-flow example with at least one record.
    assert report.imported >= 1
