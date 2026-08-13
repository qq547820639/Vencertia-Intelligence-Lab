"""Vencertia Adaptive Decision System v1.5.0.

A calibration-first decision runtime for high-uncertainty venture decisions.

Three layers:
  REALITY                — canonical truth (domain objects, persisted by repositories)
  DECISION INTELLIGENCE  — deterministic engines (belief/decision/convergence/calibration)
  CAPABILITY             — replaceable adapters (LLM/search/retrieval), no write authority
"""

from __future__ import annotations

# v1.1.2 (P1-12): single source of truth for the runtime version. pyproject.toml
# and importlib.metadata must agree (enforced by tests/test_integrity_v112.py).
__version__ = "1.5.0"
# API contract version (minor-level). The FastAPI app and /health expose it
# dynamically; legacy "version"/"api_version" health keys are derived aliases.
# Kept at "1.4" through the v1.5 structural refactor — no API contract change.
__api_contract_version__ = "1.4"
