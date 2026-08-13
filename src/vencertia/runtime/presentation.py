"""Deprecated re-export shim for the presentation layer (v1.5 refactor).

The presentation projection moved to :mod:`vencertia.presentation` (its own
top-level package, outside the deterministic ``runtime`` engine layer). This
module re-exports the public surface so every existing import path keeps
working unchanged.

.. deprecated:: 1.5.0
    New code must ``from vencertia.presentation import ...``. This shim will be
    removed in a future version.
"""

from __future__ import annotations

from vencertia.presentation import (
    ACTION_STATE_ZH,
    BELIEF_RELATION_ZH,
    CALIBRATION_MIN_SAMPLES,
    CALIBRATION_STATUS_ZH,
    CRITIQUE_FINDING_ZH,
    DECISION_TYPE_ZH,
    ENTITY_ZH,
    MODEL_RISK_ZH,
    PROBABILITY_BANDS,
    PROVENANCE_ZH,
    PROVIDER_ERROR_ZH,
    RESEARCH_STOP_STATUS_ZH,
    STAKES_CLASS_ZH,
    calibration_summary,
    critique_summary,
    estimate_phrase,
    experiment_voi_summary,
    localize_error_message,
    personalization_summary,
    probability_level,
    project_advanced_view,
    solve_summary,
)

__all__ = [
    "ACTION_STATE_ZH",
    "BELIEF_RELATION_ZH",
    "CALIBRATION_MIN_SAMPLES",
    "CALIBRATION_STATUS_ZH",
    "CRITIQUE_FINDING_ZH",
    "DECISION_TYPE_ZH",
    "ENTITY_ZH",
    "MODEL_RISK_ZH",
    "PROBABILITY_BANDS",
    "PROVIDER_ERROR_ZH",
    "PROVENANCE_ZH",
    "RESEARCH_STOP_STATUS_ZH",
    "STAKES_CLASS_ZH",
    "calibration_summary",
    "critique_summary",
    "estimate_phrase",
    "experiment_voi_summary",
    "localize_error_message",
    "personalization_summary",
    "probability_level",
    "project_advanced_view",
    "solve_summary",
]
