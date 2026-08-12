"""Application settings.

All settings are read from environment variables (``VENCERTIA_*``) with
deterministic defaults, so the system runs fully offline out of the box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration (frozen dataclass, env-overridable)."""

    # Persistence
    db_dsn: str = "sqlite:///data/vencertia.db"
    postgres_dsn: Optional[str] = None

    # Model gateway
    model_provider: str = "mock"  # mock | openai_compatible
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Policy
    policy_version: str = "1.0"
    log_level: str = "INFO"

    # Engine knobs [H2] (heuristics, configurable)
    max_pseudo_observations: float = 3.0
    conflict_weight_threshold: float = 0.3
    risk_aversion: float = 0.25
    minimum_margin: float = 0.08
    max_critical_uncertainty: float = 0.45
    transferability_threshold: float = 0.6
    experiment_max_results: int = 5
    ece_bins: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from the process environment (VENCERTIA_* variables)."""
        return cls(
            db_dsn=os.environ.get("VENCERTIA_DB_DSN", "sqlite:///data/vencertia.db"),
            postgres_dsn=os.environ.get("VENCERTIA_PG_DSN") or None,
            model_provider=os.environ.get("VENCERTIA_MODEL_PROVIDER", "mock"),
            openai_base_url=os.environ.get("VENCERTIA_OPENAI_BASE_URL") or None,
            openai_api_key=os.environ.get("VENCERTIA_OPENAI_API_KEY") or None,
            openai_model=os.environ.get("VENCERTIA_OPENAI_MODEL", "gpt-4o-mini"),
            policy_version=os.environ.get("VENCERTIA_POLICY_VERSION", "1.0"),
            log_level=os.environ.get("VENCERTIA_LOG_LEVEL", "INFO"),
            max_pseudo_observations=_env_float("VENCERTIA_MAX_PSEUDO_OBSERVATIONS", 3.0),
            conflict_weight_threshold=_env_float("VENCERTIA_CONFLICT_WEIGHT_THRESHOLD", 0.3),
            risk_aversion=_env_float("VENCERTIA_RISK_AVERSION", 0.25),
            minimum_margin=_env_float("VENCERTIA_MINIMUM_MARGIN", 0.08),
            max_critical_uncertainty=_env_float("VENCERTIA_MAX_CRITICAL_UNCERTAINTY", 0.45),
            transferability_threshold=_env_float("VENCERTIA_TRANSFERABILITY_THRESHOLD", 0.6),
            experiment_max_results=_env_int("VENCERTIA_EXPERIMENT_MAX_RESULTS", 5),
            ece_bins=_env_int("VENCERTIA_ECE_BINS", 10),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings.from_env()
