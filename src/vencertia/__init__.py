"""Vencertia Adaptive Decision System v1.0.

A calibration-first decision runtime for high-uncertainty venture decisions.

Three layers:
  REALITY                — canonical truth (domain objects, persisted by repositories)
  DECISION INTELLIGENCE  — deterministic engines (belief/decision/convergence/calibration)
  CAPABILITY             — replaceable adapters (LLM/search/retrieval), no write authority
"""

from __future__ import annotations

__version__ = "1.0.0"
