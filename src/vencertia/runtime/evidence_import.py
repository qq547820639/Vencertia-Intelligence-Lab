"""Evidence batch import — Candidate → Validation → persistence pipeline.

Every imported record goes through ``EvidencePolicy.grade`` (validation) →
``EvidenceDedupEngine.group`` (dedup) → ``repo.add_evidence`` (persistence);
the policy/dedup gates are never bypassed. Idempotency is keyed on
``content_fingerprint``: a record whose fingerprint already exists in the store
(or appears twice within a batch) is skipped and counted as ``deduplicated``,
never written twice.

JSON parsing uses only the standard library (JSON array or JSONL) per the
zero-new-dependencies ruling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from vencertia.domain import Evidence, Scope, VencertiaBaseModel
from vencertia.repositories.base import Repository
from vencertia.runtime.evidence_dedup import EvidenceDedupEngine
from vencertia.runtime.evidence_policy import EvidencePolicy


class EvidenceImportReport(VencertiaBaseModel):
    """Import report DTO — imported/deduplicated/conflicts/bound/unbound totals."""

    total: int = 0
    imported: int = 0
    deduplicated: int = 0
    conflicts: int = 0
    bound: int = 0
    unbound: int = 0
    imported_ids: list[str] = Field(default_factory=list)
    dropped_ids: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)


def _scope_value(evidence: Evidence) -> str:
    return evidence.scope.value if hasattr(evidence.scope, "value") else str(evidence.scope)


@dataclass
class EvidenceImporter:
    """Batch evidence importer wired to the policy/dedup/repo pipeline."""

    repo: Repository
    policy: EvidencePolicy
    dedup: EvidenceDedupEngine
    _project_id: str | None = field(default=None, init=False)

    # -- file loading --------------------------------------------------------

    @staticmethod
    def load_file(path: Path) -> tuple[list[Evidence], list[dict]]:
        """Parse a JSON array or JSONL file into ``(legal items, invalid rows)``."""
        return EvidenceImporter._parse(path.read_text(encoding="utf-8"))

    @staticmethod
    def _parse(text: str) -> tuple[list[Evidence], list[dict]]:
        """Parse JSON text (top-level array OR JSONL) into validated Evidence."""
        items: list[Evidence] = []
        invalid: list[dict] = []
        stripped = (text or "").strip()
        if not stripped:
            return items, invalid

        if stripped.startswith("["):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                return items, [{"index": 0, "reason": f"invalid JSON: {exc}"}]
            if not isinstance(payload, list):
                return items, [{"index": 0, "reason": "top-level JSON must be an array or JSONL"}]
            for index, row in enumerate(payload):
                EvidenceImporter._coerce(row, index, items, invalid)
            return items, invalid

        # JSONL: one JSON object per non-blank line.
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid.append({"index": line_no, "reason": f"invalid JSON: {exc}"})
                continue
            EvidenceImporter._coerce(row, line_no, items, invalid)
        return items, invalid

    @staticmethod
    def _coerce(
        row: object, index: int, items: list[Evidence], invalid: list[dict]
    ) -> None:
        if not isinstance(row, dict):
            invalid.append({"index": index, "reason": "row is not a JSON object"})
            return
        try:
            items.append(Evidence.model_validate(row))
        except Exception as exc:  # noqa: BLE001 - surface any validation error as invalid
            invalid.append({"index": index, "id": row.get("id"), "reason": str(exc)})

    # -- tenant ownership backfill -------------------------------------------

    def _ensure_project_id(self, evidence: Evidence, project_id: str | None) -> Evidence:
        """Backfill ``project_id`` for PROJECT/CUSTOMER evidence (v1.1.2 iron rule).

        Order: caller-supplied ``project_id`` → first claim's owner → leave
        missing so ``repo.add_evidence`` raises ``ValueError`` (never silently
        loosens the tenant-isolation write boundary).
        """
        if evidence.project_id:
            return evidence
        if _scope_value(evidence) not in (Scope.PROJECT.value, Scope.CUSTOMER.value):
            return evidence
        if project_id is not None:
            return evidence.model_copy(update={"project_id": project_id})
        for claim_id in evidence.claim_ids or []:
            claim = self.repo.get_claim(claim_id)
            if claim is not None and claim.project_id:
                return evidence.model_copy(update={"project_id": claim.project_id})
        return evidence

    # -- import ---------------------------------------------------------------

    def import_batch(
        self, items: list[Evidence], project_id: str | None = None
    ) -> EvidenceImportReport:
        """Import a batch through policy → dedup → persist, idempotent on fingerprint."""
        report = EvidenceImportReport(total=len(items))
        index_by_id = {e.id: i for i, e in enumerate(items)}

        # 1) Batch-internal exact-fingerprint dedup.
        kept: list[Evidence] = list(items)
        if items:
            dedup_result = self.dedup.group(items)
            kept_ids = set(dedup_result.kept_ids)
            report.dropped_ids.extend(dedup_result.dropped_ids)
            report.deduplicated += len(dedup_result.dropped_ids)
            kept = [e for e in items if e.id in kept_ids]

        # 2) Idempotency against the existing store (same fingerprint → skip).
        existing_fingerprints = {
            e.content_fingerprint for e in self.repo.list_evidence() if e.content_fingerprint
        }
        to_ingest: list[Evidence] = []
        for evidence in kept:
            if evidence.content_fingerprint and evidence.content_fingerprint in existing_fingerprints:
                report.deduplicated += 1
                report.dropped_ids.append(evidence.id)
                continue
            to_ingest.append(evidence)

        # 3) Validation gate (policy.grade) + 4) persistence (policy.apply_authority).
        for evidence in to_ingest:
            candidate = self._ensure_project_id(evidence, project_id)
            grade = self.policy.grade(candidate)
            if grade.scope_gate == "REJECTED":
                report.conflicts += 1
                report.rejected.append(
                    {
                        "index": index_by_id.get(candidate.id, 0),
                        "id": candidate.id,
                        "reason": grade.reason,
                    }
                )
                continue
            graded = self.policy.apply_authority(candidate, self.policy.version())
            self.repo.add_evidence(graded)
            report.imported += 1
            report.imported_ids.append(graded.id)
            if graded.claim_ids:
                report.bound += 1
            else:
                report.unbound += 1

        return report
