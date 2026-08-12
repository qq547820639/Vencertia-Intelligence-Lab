"""OpenAI-compatible provider (httpx) — no real API calls in tests.

``generate_structured`` requests ``response_format=json_schema`` when the
endpoint supports it, otherwise falls back to prompt-constrained JSON parsing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from vencertia.config import Settings, get_settings


class OpenAICompatibleProvider:
    """Client for any OpenAI-compatible chat completions endpoint."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.base_url = (base_url or cfg.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or cfg.openai_api_key or ""
        self.model = model or cfg.openai_model
        self.timeout = timeout

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
        # Prefer native json_schema; fall back to prompt constraints.
        if schema:
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
        return self._parse_json(raw).get("content", "")

    def _chat(self, payload: dict) -> str:
        with self._client() as client:
            response = client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - remote contract
            raise ValueError(f"Unexpected chat completion payload: {data}") from exc

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        # Strip markdown fences if present.
        if text.startswith("```"):
            text = text.strip("`")
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Best-effort: extract the first {...} block.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise
