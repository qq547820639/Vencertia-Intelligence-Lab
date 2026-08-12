"""Application settings.

All settings are read from environment variables (``VENCERTIA_*``) with
deterministic defaults, so the system runs fully offline out of the box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

# Default context-ranking weights (ADR-010). The 10 dimensions are all
# deterministic in the baseline; ``semantic`` is only active when a
# SemanticRanker adapter is registered (vector store per ADR-006).
DEFAULT_CONTEXT_RANK_WEIGHTS: dict[str, float] = {
    "scope_match": 0.15,
    "decision_relevance": 0.20,
    "belief_dependency": 0.10,
    "authority": 0.15,
    "evidence_strength": 0.10,
    "temporal_validity": 0.05,
    "recency": 0.10,
    "conflict": 0.05,
    "semantic": 0.05,
    "information_value": 0.05,
}


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
    postgres_dsn: str | None = None

    # Model gateway
    model_provider: str = "mock"  # mock | openai_compatible
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Policy
    # NOTE: the default stays "1.0" for backward compatibility with the v1.0
    # prediction ledger contract (test_register_creates_snapshot asserts
    # policy_version == "1.0"). v1.1 policy identity is carried by the new
    # record types (BeliefUpdateRecord.policy_version="1.1") and can be
    # switched globally with VENCERTIA_POLICY_VERSION=1.1.
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

    # -- v1.1 research pipeline ----------------------------------------------
    research_max_questions: int = 3
    research_max_rounds: int = 3
    research_queries_per_round: int = 3
    research_stop_marginal_value: float = 0.02
    research_stop_duplicate_rate: float = 0.5

    # -- v1.1 claim binding ---------------------------------------------------
    binding_confidence_threshold: float = 0.6
    binding_auto_retry: bool = False

    # -- v1.1 context / ranking ------------------------------------------------
    semantic_rank_provider: str = "deterministic"
    context_rank_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_CONTEXT_RANK_WEIGHTS)
    )

    # -- v1.1 evidence pipeline ------------------------------------------------
    dedup_similarity_threshold: float = 0.8
    freshness_half_life_days: float = 90.0

    # -- v1.1 decision sensitivity ---------------------------------------------
    sensitivity_step: float = 0.01
    robustness_margin_threshold: float = 0.05

    # -- v1.1 provider resilience / observability ------------------------------
    provider_max_retries: int = 2
    provider_timeout_seconds: float = 30.0
    provider_retry_backoff_base: float = 0.5
    call_log_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from the process environment (VENCERTIA_* variables)."""
        weights = dict(DEFAULT_CONTEXT_RANK_WEIGHTS)
        raw_weights = os.environ.get("VENCERTIA_CONTEXT_RANK_WEIGHTS")
        if raw_weights:
            try:
                parsed = dict(
                    (k.strip(), float(v))
                    for k, v in (part.split("=", 1) for part in raw_weights.split(",") if "=" in part)
                )
                weights.update(parsed)
            except ValueError:  # pragma: no cover - malformed env must not crash
                weights = dict(DEFAULT_CONTEXT_RANK_WEIGHTS)
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
            research_max_questions=_env_int("VENCERTIA_RESEARCH_MAX_QUESTIONS", 3),
            research_max_rounds=_env_int("VENCERTIA_RESEARCH_MAX_ROUNDS", 3),
            research_queries_per_round=_env_int("VENCERTIA_RESEARCH_QUERIES_PER_ROUND", 3),
            research_stop_marginal_value=_env_float(
                "VENCERTIA_RESEARCH_STOP_MARGINAL_VALUE", 0.02
            ),
            research_stop_duplicate_rate=_env_float(
                "VENCERTIA_RESEARCH_STOP_DUPLICATE_RATE", 0.5
            ),
            binding_confidence_threshold=_env_float(
                "VENCERTIA_BINDING_CONFIDENCE_THRESHOLD", 0.6
            ),
            binding_auto_retry=_env_bool("VENCERTIA_BINDING_AUTO_RETRY", False),
            semantic_rank_provider=os.environ.get(
                "VENCERTIA_SEMANTIC_RANK_PROVIDER", "deterministic"
            ),
            context_rank_weights=weights,
            dedup_similarity_threshold=_env_float("VENCERTIA_DEDUP_SIMILARITY_THRESHOLD", 0.8),
            freshness_half_life_days=_env_float("VENCERTIA_FRESHNESS_HALF_LIFE_DAYS", 90.0),
            sensitivity_step=_env_float("VENCERTIA_SENSITIVITY_STEP", 0.01),
            robustness_margin_threshold=_env_float(
                "VENCERTIA_ROBUSTNESS_MARGIN_THRESHOLD", 0.05
            ),
            provider_max_retries=_env_int("VENCERTIA_PROVIDER_MAX_RETRIES", 2),
            provider_timeout_seconds=_env_float("VENCERTIA_PROVIDER_TIMEOUT_SECONDS", 30.0),
            provider_retry_backoff_base=_env_float(
                "VENCERTIA_PROVIDER_RETRY_BACKOFF_BASE", 0.5
            ),
            call_log_enabled=_env_bool("VENCERTIA_CALL_LOG_ENABLED", True),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings.from_env()
