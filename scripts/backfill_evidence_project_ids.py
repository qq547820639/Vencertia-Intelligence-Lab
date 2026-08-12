#!/usr/bin/env python3
"""Backfill evidence project_id for legacy PROJECT/CUSTOMER evidence (P0-3).

v1.1.2 migration helper (docs/v1.1.2-design.md §6.3 step 5):
  - Rows with ``project_id=None`` and scope ∈ {PROJECT, CUSTOMER} are resolved
    by looking up their claim_ids → Claim.project_id (the first resolvable
    claim wins). Rows that cannot be resolved keep ``project_id=None`` and are
    marked ``UNASSIGNED`` in the audit output — they stay OUT of every project
    context at the read boundary (ADR-014).
  - Shared external evidence (WORLD/MARKET/COMPANY_CASE) is left untouched.

Usage:
  PYTHONPATH=src python scripts/backfill_evidence_project_ids.py [--db DSN] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from vencertia.config import get_settings
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository


def _repo(db: str | None):
    if db:
        return SQLiteRepository(db)
    settings = get_settings()
    if settings.db_dsn == "sqlite:///:memory:" or settings.db_dsn == ":memory:":
        return InMemoryRepository()
    return SQLiteRepository(settings.db_dsn)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="sqlite DSN (default from settings)")
    parser.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = parser.parse_args()

    repo = _repo(args.db)
    claims = repo.list_claims()
    claim_to_project = {c.id: c.project_id for c in claims if c.project_id}

    evidence_rows = repo.list_evidence()
    backfilled = 0
    unassigned = 0
    skipped = 0
    by_scope: Counter = Counter()

    for evidence in evidence_rows:
        scope = evidence.scope.value if hasattr(evidence.scope, "value") else str(evidence.scope)
        by_scope[scope] += 1
        if evidence.project_id is not None:
            skipped += 1
            continue
        if scope not in ("PROJECT", "CUSTOMER"):
            skipped += 1  # shared external evidence stays shared
            continue
        resolved = None
        for cid in (evidence.claim_ids or []):
            if cid in claim_to_project:
                resolved = claim_to_project[cid]
                break
        if resolved is None:
            unassigned += 1
            print(f"UNASSIGNED: {evidence.id} (scope={scope}, claims={evidence.claim_ids})")
            continue
        backfilled += 1
        if not args.dry_run:
            updated = evidence.model_copy(update={"project_id": resolved})
            repo.add_evidence(updated, allow_missing_project=True)

    print(
        f"{'DRY-RUN ' if args.dry_run else ''}backfill complete: "
        f"backfilled={backfilled} unassigned={unassigned} already_set={skipped}"
    )
    print(f"evidence by scope: {dict(by_scope)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
