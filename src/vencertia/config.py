"""Application settings.

All settings are read from environment variables (``VENCERTIA_*``) with
deterministic defaults, so the system runs fully offline out of the box.
"""

from __future__ import annotations

import os
import warnings
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

    # Search gateway (GAP-02): mock | http
    search_provider: str = "mock"
    search_url: str | None = None
    search_api_key: str | None = None
    search_timeout_seconds: float = 15.0

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
    calibration_min_samples: int = 20

    # -- v1.1 research pipeline ----------------------------------------------
    research_max_questions: int = 3
    research_max_rounds: int = 3
    research_queries_per_round: int = 3
    research_stop_marginal_value: float = 0.02
    research_stop_duplicate_rate: float = 0.5

    # -- v1.1 claim binding ---------------------------------------------------
    binding_confidence_threshold: float = 0.6
    binding_auto_retry: bool = False

    # -- v1.1.1 binding four-state thresholds (GAP-01) -------------------------
    # Minimum match score for a candidate claim to be considered reliable
    # (below this → UNBOUND_EVIDENCE, not silently bound).
    binding_min_score: float = 0.7
    # Top-1/top-2 gap below which the binding is AMBIGUOUS (never force top-1).
    binding_ambiguity_margin: float = 0.1
    # Match scores below this are treated as noise (not even recorded as
    # candidates). REJECTED is reserved for rule violations on real candidates.
    binding_reject_threshold: float = 0.4

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
    robustness_margin_threshold: float = 0.05  # deprecated (pre-GAP-03)

    # -- v1.1.1 three-level robustness thresholds (GAP-03) ----------------------
    fragile_flip_threshold: float = 0.10
    fragile_margin: float = 0.05
    moderate_flip_threshold: float = 0.25
    moderate_margin: float = 0.12

    # -- v1.1 provider resilience / observability ------------------------------
    provider_max_retries: int = 2
    provider_timeout_seconds: float = 30.0
    provider_retry_backoff_base: float = 0.5
    call_log_enabled: bool = True

    # -- v1.1.2 integrity / optional engines ------------------------------------
    # OpportunityCostEngine verdict (P1-9): AVAILABLE ENGINE / NOT ACTIVE BY
    # DEFAULT. solve() updates option.opportunity_cost from the founder
    # portfolio ONLY when this flag is enabled; default False = zero behavior
    # change.
    opportunity_cost_enabled: bool = False

    # -- v1.2 stakes / critic ---------------------------------------------------
    # Three-band ABSTAIN thresholds (V-4). MEDIUM == the v1.1.2 global values,
    # so a decision without explicit stakes reproduces prior behavior exactly.
    stakes_thresholds: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "HIGH": {"minimum_margin": 0.12, "max_critical_uncertainty": 0.35},
        "MEDIUM": {"minimum_margin": 0.08, "max_critical_uncertainty": 0.45},
        "LOW": {"minimum_margin": 0.04, "max_critical_uncertainty": 0.60},
    })
    # V-3: a mandatory model critic is required when stakes_class >= this value.
    critic_required_stakes: str = "HIGH"

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from the process environment (VENCERTIA_* variables)."""
        weights = dict(DEFAULT_CONTEXT_RANK_WEIGHTS)
        # M0-1: prefer VENCERTIA_MODEL_PROVIDER; fall back to the deprecated
        # MODEL_PROVIDER alias with a warning (never silently downgrade to mock).
        model_provider = os.environ.get("VENCERTIA_MODEL_PROVIDER")
        if model_provider is None:
            legacy = os.environ.get("MODEL_PROVIDER")
            if legacy:
                warnings.warn(
                    "MODEL_PROVIDER is deprecated; use VENCERTIA_MODEL_PROVIDER",
                    DeprecationWarning,
                    stacklevel=2,
                )
                model_provider = legacy
        model_provider = model_provider or "mock"
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
            model_provider=model_provider,
            openai_base_url=os.environ.get("VENCERTIA_OPENAI_BASE_URL") or None,
            openai_api_key=os.environ.get("VENCERTIA_OPENAI_API_KEY") or None,
            openai_model=os.environ.get("VENCERTIA_OPENAI_MODEL", "gpt-4o-mini"),
            search_provider=os.environ.get("VENCERTIA_SEARCH_PROVIDER", "mock"),
            search_url=os.environ.get("VENCERTIA_SEARCH_URL") or None,
            search_api_key=os.environ.get("VENCERTIA_SEARCH_API_KEY") or None,
            search_timeout_seconds=_env_float("VENCERTIA_SEARCH_TIMEOUT", 15.0),
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
            calibration_min_samples=_env_int("VENCERTIA_CALIBRATION_MIN_SAMPLES", 20),
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
            binding_min_score=_env_float("VENCERTIA_BINDING_MIN_SCORE", 0.7),
            binding_ambiguity_margin=_env_float(
                "VENCERTIA_BINDING_AMBIGUITY_MARGIN", 0.1
            ),
            binding_reject_threshold=_env_float(
                "VENCERTIA_BINDING_REJECT_THRESHOLD", 0.4
            ),
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
            fragile_flip_threshold=_env_float("VENCERTIA_FRAGILE_FLIP_THRESHOLD", 0.10),
            fragile_margin=_env_float("VENCERTIA_FRAGILE_MARGIN", 0.05),
            moderate_flip_threshold=_env_float("VENCERTIA_MODERATE_FLIP_THRESHOLD", 0.25),
            moderate_margin=_env_float("VENCERTIA_MODERATE_MARGIN", 0.12),
            provider_max_retries=_env_int("VENCERTIA_PROVIDER_MAX_RETRIES", 2),
            provider_timeout_seconds=_env_float("VENCERTIA_PROVIDER_TIMEOUT_SECONDS", 30.0),
            provider_retry_backoff_base=_env_float(
                "VENCERTIA_PROVIDER_RETRY_BACKOFF_BASE", 0.5
            ),
            call_log_enabled=_env_bool("VENCERTIA_CALL_LOG_ENABLED", True),
            opportunity_cost_enabled=_env_bool("VENCERTIA_OPPORTUNITY_COST_ENABLED", False),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings.from_env()
