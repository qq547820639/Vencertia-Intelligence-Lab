"""Provider error taxonomy (ADR-012): structured, retryable failure classes.

Kept in its own module so both ``providers.factory`` and
``providers.openai_compatible`` can import it without circularity.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for structured provider failures."""

    error_type = "PROVIDER_ERROR"

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message or self.error_type)


class ProviderTimeoutError(ProviderError):
    error_type = "TIMEOUT"


class ProviderRateLimitError(ProviderError):
    error_type = "RATE_LIMIT"


class ProviderInvalidJSONError(ProviderError):
    error_type = "INVALID_JSON"


class ProviderSchemaMismatchError(ProviderError):
    error_type = "SCHEMA_MISMATCH"


class ProviderUnavailableError(ProviderError):
    error_type = "UNAVAILABLE"


class ProviderEmptyResultError(ProviderError):
    error_type = "EMPTY_RESULT"


class ProviderPartialResultError(ProviderError):
    error_type = "PARTIAL_RESULT"


__all__ = [
    "ProviderEmptyResultError",
    "ProviderError",
    "ProviderInvalidJSONError",
    "ProviderPartialResultError",
    "ProviderRateLimitError",
    "ProviderSchemaMismatchError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
