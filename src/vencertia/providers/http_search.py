"""HttpSearchProvider — generic HTTP search adapter (GAP-02).

A user-supplied endpoint is called (``VENCERTIA_SEARCH_URL``); the response is
normalized into the internal :class:`~vencertia.providers.models.SearchResult`
shape. No commercial search vendor is bundled and no vendor DTO ever leaks
into the domain: every response field is mapped explicitly.

Response contract (documented, not enforced by any external schema):
  * either a top-level JSON array of result objects
  * or an object with a ``results`` (or ``items``/``data``) array

Each result object may carry any of:
  ``title`` (required), ``url``/``link``, ``snippet``/``summary``,
  ``content``/``body``, ``published_at``/``date``, ``source``/``site``,
  plus arbitrary extra fields preserved under ``metadata``.

Failure semantics (ADR-012 taxonomy, all structured):
  - non-200 status  → ProviderUnavailableError / ProviderRateLimitError / ...
  - non-JSON body   → ProviderInvalidJSONError
  - malformed JSON  → ProviderInvalidJSONError
  - empty result    → ProviderEmptyResultError
  - schema mismatch → ProviderSchemaMismatchError
  - partial result  → ProviderPartialResultError
No failure ever fabricates evidence; callers must handle the error
(graceful degradation, never a silent fallback to the mock provider).

Documented boundary (MINOR-PR-003): a JSON array whose items are ALL
non-dicts (e.g. ``["a", 42]``) is filtered to no usable items and reported as
``ProviderEmptyResultError`` — not ``ProviderSchemaMismatchError``. It is
never data-loss (no evidence is fabricated); a dict array with unusable
titles maps to ``ProviderSchemaMismatchError``.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from vencertia.config import Settings
from vencertia.providers.errors import (
    ProviderEmptyResultError,
    ProviderError,
    ProviderInvalidJSONError,
    ProviderPartialResultError,
    ProviderRateLimitError,
    ProviderSchemaMismatchError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from vencertia.providers.models import SearchResult

_RESULT_KEYS = (
    "results",
    "items",
    "data",
    "hits",
    "documents",
)


def _first(keys: tuple[str, ...], item: dict) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _normalize_item(raw: dict) -> SearchResult | None:
    """Map one external result object to SearchResult (None if unusable)."""
    title = _first(("title", "name", "heading"), raw)
    if not title:
        return None
    url = _first(("url", "link", "href", "permalink"), raw)
    snippet = _first(("snippet", "summary", "description", "abstract"), raw)
    content = _first(("content", "body", "text", "full_text"), raw)
    source = _first(("source", "site", "domain", "publisher"), raw)
    published_at = _parse_datetime(
        raw.get("published_at")
        or raw.get("date")
        or raw.get("published")
        or raw.get("timestamp")
    )
    return SearchResult(
        title=title,
        url=url,
        snippet=snippet,
        content=content,
        published_at=published_at,
        source=source,
        metadata=dict(raw),
    )


def _extract_items(payload) -> list[dict]:
    """Pull the result-array from a decoded JSON payload."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in _RESULT_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # A single result object is accepted as a one-element list.
        if any(k in payload for k in ("title", "url", "link", "snippet", "content")):
            return [payload]
    raise ProviderSchemaMismatchError(
        "search response is neither a list nor an object with a results array"
    )


class HttpSearchProvider:
    """Generic HTTP search adapter (httpx); normalized SearchResult output."""

    name = "http_search"

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = 15.0,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.settings = settings
        self._client = client  # injectable for tests (httpx.MockTransport)

    # -- public contract -------------------------------------------------------

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Execute a search query and normalize the response to SearchResult[]."""
        if not self.url:
            raise ProviderUnavailableError(
                "http_search requires a search endpoint (VENCERTIA_SEARCH_URL)"
            )
        try:
            payload = self._fetch(query)
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"search timed out after {self.timeout}s: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 429:
                raise ProviderRateLimitError(f"search rate limited (429): {exc}") from exc
            raise ProviderUnavailableError(f"search http error {status}: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(f"search connection error: {exc}") from exc

        items = _extract_items(payload)
        if not items:
            raise ProviderEmptyResultError("search returned no results")

        normalized: list[SearchResult] = []
        invalid = 0
        for item in items:
            result = _normalize_item(item)
            if result is None:
                invalid += 1
            else:
                normalized.append(result)
        if not normalized and invalid:
            raise ProviderSchemaMismatchError(
                f"search returned {invalid} result(s) but none carried a usable title"
            )
        if invalid:
            # Some items are unusable: the set cannot be trusted as complete.
            raise ProviderPartialResultError(
                f"search returned {invalid} invalid result(s) out of {len(items)}"
            )
        return normalized[:k]

    # -- transport -------------------------------------------------------------

    def _fetch(self, query: str) -> object:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self._client is not None:
            response = self._client.get(self.url, params={"q": query}, headers=headers)
        else:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self.url, params={"q": query}, headers=headers)
        response.raise_for_status()
        return self._decode(response)

    @staticmethod
    def _decode(response: httpx.Response) -> object:
        content_type = response.headers.get("content-type", "")
        text = response.text
        if not text or not text.strip():
            raise ProviderEmptyResultError("search returned an empty body")
        if "json" not in content_type and not text.lstrip().startswith(("{", "[")):
            raise ProviderInvalidJSONError(
                f"search response is not JSON (content-type={content_type!r})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderInvalidJSONError(f"malformed JSON in search response: {exc}") from exc


__all__ = ["HttpSearchProvider"]
