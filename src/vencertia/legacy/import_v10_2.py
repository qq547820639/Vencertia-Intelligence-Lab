"""V10.2 release importer — read-only scan + idempotent import.

Reads the AgentV10.2 Full Release directory (User Knowledge Runtime V1.0 and
Company Intelligence Runtime V1.1) and maps its semantic assets into v1.0
canonical objects. The source directory is never modified.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from vencertia.domain import CompanyCase, Evidence, MemoryRecord, Rule, Scope, utcnow
from vencertia.events.types import DomainEvent, EventType
from vencertia.legacy import mapping
from vencertia.legacy.mapping import MAPPING_VERSION
from vencertia.repositories.base import EntityNotFoundError, Repository

if TYPE_CHECKING:  # pragma: no cover - type-only import
    from vencertia.runtime.evidence_policy import EvidencePolicy


class ImportManifestEntry(BaseModel):
    source_ref: str
    canonical_type: str
    canonical_id: str
    mapping_version: str = MAPPING_VERSION
    warnings: list[str] = Field(default_factory=list)


class ImportManifest(BaseModel):
    source_dir: str = ""
    entries: list[ImportManifestEntry] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=utcnow)

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def core_objects(self) -> int:
        return sum(1 for e in self.entries if e.canonical_type in {"memory", "company_case"})


class ImportReport(BaseModel):
    manifest: ImportManifest
    imported: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    coverage: float = 0.0  # mapped / found
    warnings: list[str] = Field(default_factory=list)


@dataclass
class V10_2Importer:
    """Scans and imports the V10.2 release directory (read-only on source)."""

    source_dir: Path
    repo: Repository
    policy: Optional[Any] = None  # EvidencePolicy (optional; type-only import)

    # -- location helpers ----------------------------------------------------

    @property
    def release_dir(self) -> Path:
        return Path(self.source_dir)

    @property
    def user_runtime_dir(self) -> Path:
        return self.release_dir / "User Knowledge Runtime V1.0"

    @property
    def company_runtime_dir(self) -> Path:
        return self.release_dir / "Company Intelligence Runtime V1.1"

    def _find_memory_flow_files(self) -> list[Path]:
        examples = self.user_runtime_dir / "examples"
        if not examples.exists():
            return []
        return sorted(
            p
            for p in examples.glob("*.json")
            if "output" in p.name or "memory" in p.name.lower()
        )

    def _find_company_schema_files(self) -> list[Path]:
        schema_dir = self.company_runtime_dir / "json_schema"
        if not schema_dir.exists():
            return []
        return sorted(schema_dir.glob("*.schema.json"))

    def _extract_memory_records(self) -> list[tuple[str, Dict[str, Any]]]:
        """Yield (source_ref, memory_record_dict) pairs from example outputs.

        Example files may contain several concatenated JSON objects, so each
        file is parsed with a streaming raw_decode loop.
        """
        records: list[tuple[str, Dict[str, Any]]] = []
        for path in self._find_memory_flow_files():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for data in _iter_json_objects(text):
                candidates = data.get("results") if isinstance(data, dict) else data
                if isinstance(candidates, list):
                    for item in candidates:
                        if isinstance(item, dict) and item.get("new_memory_record"):
                            records.append(
                                (
                                    f"{path.name}::{item.get('candidate_id', '?')}",
                                    item["new_memory_record"],
                                )
                            )
                elif isinstance(data, dict) and data.get("new_memory_record"):
                    records.append((path.name, data["new_memory_record"]))
        return records

    # -- scan ----------------------------------------------------------------

    def scan(self) -> ImportManifest:
        entries: list[ImportManifestEntry] = []
        for source_ref, record in self._extract_memory_records():
            try:
                mapped = mapping.map_memory_record(record)
                entries.append(
                    ImportManifestEntry(
                        source_ref=source_ref,
                        canonical_type="memory",
                        canonical_id=mapped.memory_id,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                entries.append(
                    ImportManifestEntry(
                        source_ref=source_ref,
                        canonical_type="memory",
                        canonical_id="?",
                        warnings=[str(exc)],
                    )
                )
        for path in self._find_company_schema_files():
            company_id = mapping.company_id_from_filename(path.name)
            entries.append(
                ImportManifestEntry(
                    source_ref=path.name,
                    canonical_type="company_case",
                    canonical_id=company_id,
                )
            )
        for rule in mapping.map_rules():
            entries.append(
                ImportManifestEntry(
                    source_ref="rules:v10.2",
                    canonical_type="rule",
                    canonical_id=rule.id,
                )
            )
        return ImportManifest(source_dir=str(self.release_dir), entries=entries)

    # -- imports -------------------------------------------------------------

    def import_memory(self) -> ImportReport:
        manifest = self.scan()
        imported = 0
        skipped = 0
        failed = 0
        warnings: list[str] = []
        for entry in manifest.entries:
            if entry.canonical_type != "memory":
                continue
            record = self._record_for_entry(entry)
            if record is None:
                failed += 1
                continue
            if self.repo.get_memory(entry.canonical_id) is not None:
                skipped += 1
                continue
            try:
                self.repo.save_memory(mapping.map_memory_record(record))
                self._emit_event("memory", entry.canonical_id, "MEMORY_IMPORTED")
                imported += 1
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                warnings.append(f"{entry.source_ref}: {exc}")
        return ImportReport(
            manifest=manifest,
            imported=imported,
            skipped_duplicates=skipped,
            failed=failed,
            coverage=self._coverage(manifest),
            warnings=warnings,
        )

    def import_company_cases(self) -> ImportReport:
        manifest = self.scan()
        imported = 0
        skipped = 0
        failed = 0
        warnings: list[str] = []
        for path in self._find_company_schema_files():
            company_id = mapping.company_id_from_filename(path.name)
            if self.repo.get_company_case(company_id) is not None:
                skipped += 1
                continue
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
                case = self._company_case_from_schema(schema, path.name)
                self.repo.save_company_case(case)
                for evidence in self._case_evidence_from_schema(schema, case.company_id):
                    self.repo.add_evidence(evidence)
                self._emit_event("company_case", case.company_id, "COMPANY_CASE_IMPORTED")
                imported += 1
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                warnings.append(f"{path.name}: {exc}")
        return ImportReport(
            manifest=manifest,
            imported=imported,
            skipped_duplicates=skipped,
            failed=failed,
            coverage=self._coverage(manifest),
            warnings=warnings,
        )

    def import_rules(self) -> ImportReport:
        manifest = self.scan()
        imported = 0
        skipped = 0
        for rule in mapping.map_rules():
            existing = self.repo.get_rules(rule.kind)
            if any(r.id == rule.id for r in existing):
                skipped += 1
                continue
            self.repo.save_rule(rule)
            imported += 1
        return ImportReport(
            manifest=manifest,
            imported=imported,
            skipped_duplicates=skipped,
            failed=0,
            coverage=self._coverage(manifest),
        )

    def import_all(self) -> ImportReport:
        """Run all three imports; combine into one report."""
        memory = self.import_memory()
        cases = self.import_company_cases()
        rules = self.import_rules()
        return ImportReport(
            manifest=self.scan(),
            imported=memory.imported + cases.imported + rules.imported,
            skipped_duplicates=memory.skipped_duplicates + cases.skipped_duplicates + rules.skipped_duplicates,
            failed=memory.failed + cases.failed + rules.failed,
            coverage=self._coverage(self.scan()),
            warnings=memory.warnings + cases.warnings + rules.warnings,
        )

    def dry_run(self) -> ImportReport:
        """Report mapping coverage without writing anything."""
        manifest = self.scan()
        return ImportReport(
            manifest=manifest,
            imported=0,
            skipped_duplicates=0,
            failed=0,
            coverage=self._coverage(manifest),
            warnings=[],
        )

    # -- internals -----------------------------------------------------------

    def _coverage(self, manifest: ImportManifest) -> float:
        if manifest.total == 0:
            return 0.0
        mapped = sum(1 for e in manifest.entries if e.canonical_id and e.canonical_id != "?")
        return round(mapped / manifest.total, 4)

    def _record_for_entry(self, entry: ImportManifestEntry) -> Dict[str, Any] | None:
        for source_ref, record in self._extract_memory_records():
            if source_ref == entry.source_ref:
                return record
        return None

    def _company_case_from_schema(self, schema: Dict[str, Any], filename: str) -> CompanyCase:
        props = schema.get("properties", {})
        company_id = mapping.company_id_from_filename(filename)
        title = schema.get("title") or props.get("canonical_name", {}).get("title") or filename
        return CompanyCase(
            company_id=company_id,
            canonical_name=title,
            case_roles=list(props.get("case_roles", {}).get("enum") or []),
            lifecycle_stage=props.get("lifecycle_stage", {}).get("default", "UNKNOWN"),
            capital_stage=props.get("capital_stage", {}).get("default", "UNKNOWN"),
            overall_confidence=props.get("overall_confidence", {}).get("default", "LOW"),
            data_completeness=props.get("data_completeness", {}).get("default", "LOW"),
            research_status=props.get("research_status", {}).get("default", "DRAFT"),
        )

    def _case_evidence_from_schema(self, schema: Dict[str, Any], company_id: str) -> list[Evidence]:
        """Generate COMPANY_CASE-scope evidence candidates from a schema."""
        title = schema.get("title") or company_id
        return [
            Evidence(
                id=f"E_{company_id}_FACT",
                claim_ids=[],
                scope=Scope.COMPANY_CASE,
                evidence_type="COMPANY_CASE_FACT",
                source=f"Imported company case schema: {title}",
                authority_level="MODEL_PRIOR",
                reliability=0.5,
                directness=0.5,
                relevance=0.5,
                strength=0.5,
                transferability=None,
            )
        ]

    def _emit_event(self, entity_type: str, entity_id: str, note: str) -> None:
        try:
            self.repo.append_event(
                DomainEvent(
                    event_type="COMPANY_CASE_UPDATED" if entity_type == "company_case" else "PROJECT_STATE_CHANGED",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    payload={"note": note, "mapping_version": MAPPING_VERSION},
                    actor="migrate-v10.2",
                )
            )
        except Exception:  # pragma: no cover - event log must not break import
            pass


# ---------------------------------------------------------------------------
# V10.2 models enum extraction (parse models.py with AST, no execution)
# ---------------------------------------------------------------------------


def _iter_json_objects(text: str):
    """Yield JSON objects from a stream of concatenated JSON documents."""
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        obj, end = decoder.raw_decode(text, index)
        yield obj
        index = end


def extract_v10_2_enums(models_py: Path) -> Dict[str, List[str]]:
    """Parse V10.2 ``models.py`` and return {EnumClassName: [members]}."""
    result: Dict[str, List[str]] = {}
    tree = ast.parse(models_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            if any("Enum" in b or "StrEnum" in b for b in bases):
                members: List[str] = []
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                                members.append(target.id)
                    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        if not stmt.target.id.startswith("_"):
                            members.append(stmt.target.id)
                result[node.name] = members
    return result


def build_mapping_dictionary(models_py: Path) -> Dict[str, Any]:
    """Generate the domain-object mapping dictionary from V10.2 enum defs."""
    enums = extract_v10_2_enums(models_py)
    return {
        "mapping_version": MAPPING_VERSION,
        "source_models": str(models_py),
        "memory_scope": {v: v for v in enums.get("MemoryScope", [])},
        "memory_type": {v: v for v in enums.get("MemoryType", [])},
        "memory_status": {v: v for v in enums.get("MemoryStatus", [])},
        "memory_operation": {v: v for v in enums.get("MemoryOperation", [])},
        "access_class": {v: v for v in enums.get("AccessClass", [])},
        "proper_store": {v: v for v in enums.get("ProperStore", [])},
        "fact_status": {v: v for v in enums.get("FactStatus", [])},
        "source_type_to_authority": {
            k: v.value for k, v in mapping.V10_2_SOURCE_TO_AUTHORITY.items()
        },
        "source_type_to_evidence_type": {
            k: v for k, v in mapping.V10_2_SOURCE_TO_EVIDENCE_TYPE.items()
        },
    }
