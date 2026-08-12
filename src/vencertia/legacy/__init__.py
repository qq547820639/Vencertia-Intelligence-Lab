"""Legacy V10.2 bridge: pure mapping functions + release importer."""

from __future__ import annotations

from vencertia.legacy.import_v10_2 import (
    ImportManifest,
    ImportManifestEntry,
    ImportReport,
    V10_2Importer,
    build_mapping_dictionary,
    extract_v10_2_enums,
)
from vencertia.legacy.mapping import (
    MAPPING_VERSION,
    PROPER_STORE_MAP,
    V10_2_SOURCE_TO_AUTHORITY,
    authority_from_v10_2_source_type,
    company_id_from_filename,
    evidence_type_from_v10_2_source_type,
    map_access_class,
    map_claim,
    map_company_case,
    map_evidence,
    map_memory_record,
    map_memory_scope,
    map_memory_status,
    map_memory_type,
    map_rules,
    map_verification,
)

__all__ = [
    "ImportManifest",
    "ImportManifestEntry",
    "ImportReport",
    "MAPPING_VERSION",
    "PROPER_STORE_MAP",
    "V10_2Importer",
    "V10_2_SOURCE_TO_AUTHORITY",
    "authority_from_v10_2_source_type",
    "build_mapping_dictionary",
    "company_id_from_filename",
    "evidence_type_from_v10_2_source_type",
    "extract_v10_2_enums",
    "map_access_class",
    "map_claim",
    "map_company_case",
    "map_evidence",
    "map_memory_record",
    "map_memory_scope",
    "map_memory_status",
    "map_memory_type",
    "map_rules",
    "map_verification",
]
