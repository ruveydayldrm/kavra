"""Provider-agnostic LLM interface.

Every provider exposes one call: `complete_json(system, user, schema)` which must return a
dict that *already* parsed as JSON. Schema validation (Pydantic) happens one level up, in
the router, so every provider is held to the same contract.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Generic provider failure."""

    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status == 429 or self.status >= 500


class QuotaExhausted(LLMError):
    """Daily quota gone: switch provider instead of waiting."""


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cached: bool = False
    raw: str = field(default="", repr=False)


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(
        self, system: str, user: str, schema: dict[str, Any], temperature: float = 0.4
    ) -> LLMResult: ...


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema -> self-contained strict schema.

    Inlines $defs, forbids extra keys and marks every property required — the shape that
    OpenAI-compatible `strict: true` endpoints (Groq) and Gemini's responseJsonSchema accept.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(copy.deepcopy(defs[name]))
            out = {k: walk(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"].keys())
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    result = walk(raw)
    assert isinstance(result, dict)
    return result


def estimate_tokens(text: str) -> int:
    # ~3.5 chars/token is a safe over-estimate for TR/EN mixed text.
    return int(len(text) / 3.5) + 1
