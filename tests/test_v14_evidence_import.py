"""v1.4 T2 — P1-2 证据批量导入（EvidencePolicy → dedup → 幂等 → 入库）。"""

from __future__ import annotations

import json

import pytest

from vencertia.config import Settings
from vencertia.domain import AuthorityLevel, Direction, Evidence
from vencertia.providers.search import content_fingerprint
from vencertia.runtime import (
    EvidenceDedupEngine,
    EvidenceImporter,
    EvidenceImportReport,
)
from vencertia.runtime.evidence_policy import EvidenceGrade


def _evidence(
    eid: str,
    source: str,
    *,
    claim_ids: list[str] | None = None,
    fp: str | None = None,
    scope: str = "PROJECT",
    evidence_type: str = "REVIEWED_EXTERNAL_RESEARCH",
    project_id: str = "PRJ_IMP",
    **kwargs,
) -> Evidence:
    payload: dict = {
        "id": eid,
        "claim_ids": claim_ids or [],
        "scope": scope,
        "evidence_type": evidence_type,
        "source": source,
        "project_id": project_id,
        "supports_or_contradicts": Direction.SUPPORTS.value,
        "directness": 0.8,
        "reliability": 0.8,
        "relevance": 1.0,
        "strength": 0.8,
        "authority_level": "MODEL_PRIOR",
        "verification": "ESTIMATED",
    }
    if fp is not None:
        payload["content_fingerprint"] = fp
    payload.update(kwargs)
    return Evidence(**payload)


def _importer(repo, policy) -> EvidenceImporter:
    return EvidenceImporter(
        repo=repo, policy=policy, dedup=EvidenceDedupEngine(Settings())
    )


def test_report_fields_contract():
    fields = set(EvidenceImportReport.model_fields)
    assert {
        "total",
        "imported",
        "deduplicated",
        "conflicts",
        "bound",
        "unbound",
        "imported_ids",
        "dropped_ids",
        "rejected",
    } <= fields


def test_basic_import(repo, policy):
    importer = _importer(repo, policy)
    items = [
        _evidence("E_1", "paid pilot 1", claim_ids=["CLM_1"], fp=content_fingerprint("a")),
        _evidence("E_2", "paid pilot 2", claim_ids=["CLM_1"], fp=content_fingerprint("b")),
        _evidence("E_3", "market signal", claim_ids=[], fp=content_fingerprint("c")),
    ]
    report = importer.import_batch(items)
    assert report.total == 3
    assert report.imported == 3
    assert report.bound == 2
    assert report.unbound == 1
    assert report.deduplicated == 0
    assert report.conflicts == 0


def test_idempotent_fingerprint_skip(repo, policy):
    importer = _importer(repo, policy)
    fp = content_fingerprint("same evidence text")
    importer.import_batch([_evidence("E_A", "same evidence text", fp=fp)])
    assert len(repo.list_evidence()) == 1
    report = importer.import_batch([_evidence("E_B", "same evidence text", fp=fp)])
    assert report.imported == 0
    assert report.deduplicated == 1
    assert len(repo.list_evidence()) == 1


def test_batch_internal_dedup(repo, policy):
    importer = _importer(repo, policy)
    fp = content_fingerprint("dup text")
    report = importer.import_batch(
        [_evidence("E_A", "dup text", fp=fp), _evidence("E_B", "dup text", fp=fp)]
    )
    assert report.imported == 1
    assert report.deduplicated == 1
    assert len(report.dropped_ids) == 1


def test_conflicts_count_on_rejected(repo, policy, monkeypatch):
    importer = _importer(repo, policy)
    evidence = _evidence("E_R", "rejected", fp=content_fingerprint("r"))

    def fake_grade(e):
        return EvidenceGrade(
            evidence=e,
            authority_level=AuthorityLevel.MODEL_PRIOR,
            effective_weight=0.0,
            scope_gate="REJECTED",
            reason="blocked by policy",
        )

    monkeypatch.setattr(importer.policy, "grade", fake_grade)
    report = importer.import_batch([evidence])
    assert report.conflicts >= 1
    assert report.rejected
    assert report.imported == 0


def test_policy_not_bypassed(repo, policy, monkeypatch):
    importer = _importer(repo, policy)
    evidence = _evidence("E_X", "x", fp=content_fingerprint("x"))

    def boom(e):
        raise RuntimeError("policy gate must run")

    monkeypatch.setattr(importer.policy, "grade", boom)
    with pytest.raises(RuntimeError):
        importer.import_batch([evidence])
    assert len(repo.list_evidence()) == 0


def test_import_applies_authority(repo, policy):
    importer = _importer(repo, policy)
    report = importer.import_batch(
        [_evidence("E_AUTH", "auth", fp=content_fingerprint("auth"))]
    )
    assert report.imported == 1
    stored = repo.get_evidence("E_AUTH")
    assert stored is not None
    assert stored.authority_level == "REVIEWED_EXTERNAL_RESEARCH"  # not MODEL_PRIOR default


def test_load_file_json_array(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "E_1",
                    "scope": "PROJECT",
                    "evidence_type": "REAL_PAYMENT",
                    "source": "paid",
                    "project_id": "PRJ",
                    "claim_ids": ["CLM_1"],
                },
                {
                    "id": "E_2",
                    "scope": "PROJECT",
                    "evidence_type": "REAL_PAYMENT",
                    "source": "paid2",
                    "project_id": "PRJ",
                },
                {"id": "E_bad", "scope": "PROJECT"},
            ]
        ),
        encoding="utf-8",
    )
    items, invalid = EvidenceImporter.load_file(path)
    assert len(items) == 2
    assert len(invalid) == 1


def test_load_file_jsonl(tmp_path):
    path = tmp_path / "evidence.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "E_1",
                "scope": "PROJECT",
                "evidence_type": "REAL_PAYMENT",
                "source": "paid",
                "project_id": "PRJ",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "E_2",
                "scope": "PROJECT",
                "evidence_type": "REAL_PAYMENT",
                "source": "paid2",
                "project_id": "PRJ",
            }
        )
        + "\nnot json\n",
        encoding="utf-8",
    )
    items, invalid = EvidenceImporter.load_file(path)
    assert len(items) == 2
    assert len(invalid) == 1


def test_api_evidence_import(api_client):
    client = api_client
    items = [
        {
            "id": "E_1",
            "scope": "PROJECT",
            "evidence_type": "REAL_PAYMENT",
            "source": "paid",
            "project_id": "PRJ_API",
            "claim_ids": ["CLM_1"],
        },
        {
            "id": "E_2",
            "scope": "PROJECT",
            "evidence_type": "REAL_PAYMENT",
            "source": "paid2",
            "project_id": "PRJ_API",
        },
    ]
    r = client.post("/v1/evidence/import", json={"items": items})
    assert r.status_code == 200
    assert r.json()["code"] == 0
    data = r.json()["data"]
    assert set(data) >= {"imported", "deduplicated", "conflicts", "bound", "unbound"}
    assert data["imported"] == 2
    assert data["bound"] == 1
    assert data["unbound"] == 1


def test_api_evidence_import_empty(api_client):
    client = api_client
    r = client.post("/v1/evidence/import", json={"items": []})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 0
    assert data["imported"] == 0
