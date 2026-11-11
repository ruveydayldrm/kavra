"""Concrete providers: Gemini (AI Studio), Groq (OpenAI-compatible), Ollama, and a fake."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from kavra.llm.base import LLMError, LLMResult, QuotaExhausted, estimate_tokens

TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("model did not return JSON") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise LLMError("JSON root must be an object")
    return data


def _retry_after(resp: httpx.Response) -> float | None:
    h = resp.headers.get("retry-after")
    if h:
        try:
            return float(h)
        except ValueError:
            pass
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', resp.text)
    return float(m.group(1)) if m else None


def _raise_for(resp: httpx.Response, provider: str) -> None:
    if resp.status_code < 400:
        return
    body = resp.text[:400]
    daily = any(s in body for s in ("PerDay", "per day", "RPD", "TPD", "daily"))
    if resp.status_code == 429 and daily:
        raise QuotaExhausted(f"{provider}: daily quota exhausted", 429)
    raise LLMError(
        f"{provider} HTTP {resp.status_code}: {body}", resp.status_code, _retry_after(resp)
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set", status=401)
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], temperature: float = 0.4
    ) -> LLMResult:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        t0 = time.perf_counter()
        resp = self.client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
        _raise_for(resp, self.name)
        payload = resp.json()
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError):
            reason = payload.get("promptFeedback") or payload.get("candidates", [{}])[0].get(
                "finishReason"
            )
            raise LLMError(f"gemini returned no content: {reason}") from None
        usage = payload.get("usageMetadata", {})
        return LLMResult(
            data=_parse_json(text),
            provider=self.name,
            model=self.model,
            tokens_in=int(usage.get("promptTokenCount", 0)),
            tokens_out=int(usage.get("candidatesTokenCount", 0)),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw=text,
        )


class OpenAICompatProvider:
    """Groq (and anything else speaking /chat/completions)."""

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        base_url: str,
        strict: bool = True,
        client: httpx.Client | None = None,
    ):
        if not api_key:
            raise LLMError(f"{name.upper()}_API_KEY is not set", status=401)
        self.name = name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.strict = strict
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], temperature: float = 0.2
    ) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": self.strict, "schema": schema},
            },
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "medium"
        t0 = time.perf_counter()
        resp = self.client.post(
            f"{self.base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        _raise_for(resp, self.name)
        payload = resp.json()
        text = payload["choices"][0]["message"].get("content") or ""
        usage = payload.get("usage", {})
        return LLMResult(
            data=_parse_json(text),
            provider=self.name,
            model=self.model,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw=text,
        )


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str, client: httpx.Client | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(600.0, connect=5.0))

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], temperature: float = 0.3
    ) -> LLMResult:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": temperature, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        t0 = time.perf_counter()
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.ConnectError as e:
            raise LLMError(f"ollama not reachable at {self.base_url}", status=503) from e
        _raise_for(resp, self.name)
        payload = resp.json()
        text = payload.get("message", {}).get("content", "")
        return LLMResult(
            data=_parse_json(text),
            provider=self.name,
            model=self.model,
            tokens_in=int(payload.get("prompt_eval_count", 0)),
            tokens_out=int(payload.get("eval_count", 0)),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw=text,
        )


class FakeProvider:
    """Deterministic provider for tests and offline demos.

    `handler(system, user, schema) -> dict` decides the answer.
    """

    def __init__(
        self,
        handler: Callable[[str, str, dict[str, Any]], dict[str, Any]],
        name: str = "fake",
        model: str = "fake-1",
    ):
        self.handler = handler
        self.name = name
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], temperature: float = 0.0
    ) -> LLMResult:
        self.calls.append((system, user))
        data = self.handler(system, user, schema)
        return LLMResult(
            data=data,
            provider=self.name,
            model=self.model,
            tokens_in=estimate_tokens(system + user),
            tokens_out=estimate_tokens(json.dumps(data)),
        )
