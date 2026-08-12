from __future__ import annotations

import json
import re
from typing import Any

from .models import MemoryCandidate, MemoryRecord


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def normalize_value(value: dict[str, Any] | None) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def exact_duplicate(candidate: MemoryCandidate, existing: MemoryRecord) -> bool:
    if candidate.proposed_memory_type != existing.memory_type:
        return False
    return (
        normalize_text(candidate.content) == normalize_text(existing.content)
        and normalize_value(candidate.structured_value) == normalize_value(existing.structured_value)
    )
