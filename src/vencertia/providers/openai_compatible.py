"""OpenAI-compatible provider (httpx) — no real API calls in tests.

``generate_structured`` requests ``response_format=json_schema`` when the
endpoint supports it, otherwise falls back to prompt-constrained JSON parsing.

Errors are mapped to the structured taxonomy in ``providers.factory``
(timeout / rate limit / invalid JSON / schema mismatch / unavailable).
A ``request_id`` is generated per call for ProviderCallRecord observability.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx

from vencertia.config import Settings, get_settings
from vencertia.providers.errors import (
    ProviderEmptyResultError,
    ProviderError,
    ProviderInvalidJSONError,
    ProviderRateLimitError,
    ProviderSchemaMismatchError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def _is_json_schema(schema: dict) -> bool:
    """A real JSON Schema has structural keywords; mock kind tags do not."""
    if not isinstance(schema, dict) or not schema:
        return False
    return any(
        key in schema
        for key in ("type", "properties", "items", "$defs", "definitions", "oneOf", "anyOf")
    )


class OpenAICompatibleProvider:
    """Client for any OpenAI-compatible chat completions endpoint."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.base_url = (base_url or cfg.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or cfg.openai_api_key or ""
        self.model = model or cfg.openai_model
        self.timeout = timeout
        self.last_request_id: str = ""

    def _client(self) -> httpx.Client:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout)

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a deterministic Vencertia capability module. "
                        "Return ONLY valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": f"{task}\nContext: {json.dumps(context, default=str)}"},
            ],
            "temperature": 0.0,
        }
        # Prefer native json_schema — but ONLY when ``schema`` is an actual
        # JSON Schema. Mock-style kind tags ({"kind": "compile_decision"}) are
        # dispatch hints, not schemas: sending them as ``json_schema`` makes
        # OpenAI-compatible endpoints reject the request (400). The kind-tag
        # path falls back to ``json_object`` + prompt constraints + local
        # ``_parse_json`` validation (v1.9 fix).
        if _is_json_schema(schema):
            payload["response_format"] = {"type": "json_schema", "json_schema": schema}
        else:
            payload["response_format"] = {"type": "json_object"}
        raw = self._chat(payload)
        return self._parse_json(raw)

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        raw = self._chat(payload)
        # ``complete`` asks for free text; a conforming endpoint returns plain
        # text, NOT JSON. Use the JSON "content" field when the response
        # happens to be JSON, otherwise return the text verbatim (v1.9 fix —
        # previously any plain-text reply raised ProviderInvalidJSONError).
        try:
            parsed = self._parse_json(raw)
        except ProviderError:
            return raw
        return str(parsed.get("content", raw))

    def _chat(self, payload: dict) -> str:
        self.last_request_id = "req_" + uuid4().hex
        try:
            with self._client() as client:
                response = client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"timeout after {self.timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise ProviderRateLimitError(str(exc)) from exc
            if exc.response is not None and 500 <= exc.response.status_code < 600:
                raise ProviderUnavailableError(str(exc)) from exc
            raise ProviderUnavailableError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise ProviderInvalidJSONError(str(exc)) from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderSchemaMismatchError(f"Unexpected chat completion payload: {data}") from exc

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if not text:
            raise ProviderEmptyResultError("empty provider response")
        # Strip markdown fences if present (incl. ```json language tags).
        if text.startswith("```"):
            text = text.lstrip("`")
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text.rstrip("`")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as outer_exc:
            # Best-effort: extract the first {...} block.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError as exc:
                    raise ProviderInvalidJSONError(str(exc)) from exc
            else:
                raise ProviderInvalidJSONError("no JSON object found in response") from outer_exc
        if not isinstance(parsed, dict):
            raise ProviderSchemaMismatchError("provider response is not a JSON object")
        return parsed
