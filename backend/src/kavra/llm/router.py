"""Role-based routing with rate limiting, retries, provider fallback and a durable cache.

    generator -> [gemini:3.8-flash, gemini:3.5-flash-lite, ollama:qwen2.5:3b]
    auditor   -> [groq:gpt-oss-120b, groq:qwen3.8-27b, gemini:3.5-flash-lite]

The router enforces the auditor != generator rule: if the generator chain fell back to the
same provider/model the auditor would use, that auditor candidate is skipped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from kavra.config import Settings, get_settings
from kavra.db import Database, get_db, now
from kavra.llm.base import (
    LLMError,
    LLMProvider,
    LLMResult,
    QuotaExhausted,
    estimate_tokens,
    strict_schema,
)
from kavra.llm.providers import GeminiProvider, OllamaProvider, OpenAICompatProvider

log = logging.getLogger("kavra.llm")
T = TypeVar("T", bound=BaseModel)
PROMPT_VERSION = "v3"


@dataclass
class Budget:
    rpm: int
    tpm: int
    rpd: int


class RateLimiter:
    """Sliding-window RPM/TPM limiter + persisted daily request counter."""

    def __init__(self, db: Database, provider: str, model: str, budget: Budget):
        self.db, self.provider, self.model, self.budget = db, provider, model, budget
        self._lock = threading.Lock()
        self._window: deque[tuple[float, int]] = deque()
        self.blocked_until = 0.0

    def _used_today(self) -> int:
        midnight = time.time() - (time.time() % 86400)
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM llm_calls WHERE provider=? AND model=? AND cached=0 AND created_at>=?",
                (self.provider, self.model, midnight),
            )
            or 0
        )

    def acquire(self, tokens: int, max_wait: float = 180.0) -> None:
        if self.budget.rpd and self._used_today() >= self.budget.rpd:
            raise QuotaExhausted(f"{self.provider}:{self.model} local daily budget reached", 429)
        deadline = time.time() + max_wait
        while True:
            with self._lock:
                t = time.time()
                while self._window and t - self._window[0][0] > 60:
                    self._window.popleft()
                reqs = len(self._window)
                toks = sum(n for _, n in self._window)
                fits = reqs < self.budget.rpm and (
                    toks + tokens <= self.budget.tpm or (reqs == 0 and tokens > self.budget.tpm)
                )
                if fits and t >= self.blocked_until:
                    self._window.append((t, tokens))
                    return
                wait = max(
                    self.blocked_until - t, 60 - (t - self._window[0][0]) if self._window else 1
                )
            if time.time() + wait > deadline:
                raise LLMError(
                    f"{self.provider}:{self.model} rate window too long ({wait:.0f}s)", 429
                )
            time.sleep(min(max(wait, 0.25), 5))


class Router:
    def __init__(
        self,
        chains: dict[str, list[LLMProvider]],
        db: Database | None = None,
        budgets: dict[str, Budget] | None = None,
        max_retries: int = 4,
        use_cache: bool = True,
    ):
        self.chains = chains
        self.db = db or get_db()
        self.budgets = budgets or {}
        self.max_retries = max_retries
        self.use_cache = use_cache
        self._limiters: dict[str, RateLimiter] = {}
        self._exhausted: dict[str, float] = {}
        self.last_generator: str | None = None

    # -- helpers ----------------------------------------------------------
    def _limiter(self, p: LLMProvider) -> RateLimiter:
        key = f"{p.name}:{p.model}"
        if key not in self._limiters:
            budget = self.budgets.get(p.name, Budget(rpm=1000, tpm=10**9, rpd=0))
            self._limiters[key] = RateLimiter(self.db, p.name, p.model, budget)
        return self._limiters[key]

    def _cache_key(self, role: str, p: LLMProvider, system: str, user: str) -> str:
        h = hashlib.sha256(f"{PROMPT_VERSION}|{role}|{p.name}:{p.model}|{system}|{user}".encode())
        return h.hexdigest()

    def _record(
        self, role: str, res: LLMResult | None, p: LLMProvider, ok: bool, status: int | None = None
    ) -> None:
        self.db.insert(
            "llm_calls",
            {
                "provider": p.name,
                "model": p.model,
                "role": role,
                "ok": int(ok),
                "status": status,
                "tokens_in": res.tokens_in if res else 0,
                "tokens_out": res.tokens_out if res else 0,
                "latency_ms": res.latency_ms if res else 0,
                "cached": int(bool(res and res.cached)),
                "created_at": now(),
            },
        )

    # -- main entry ---------------------------------------------------------
    def call(
        self,
        role: str,
        system: str,
        user: str,
        out: type[T],
        temperature: float = 0.4,
        avoid: str | None = None,
    ) -> tuple[T, LLMResult]:
        """Call the first healthy provider for `role` and validate into `out`.

        `avoid` = "provider:model" that must not be used (keeps auditor != generator).
        """
        schema = strict_schema(out)
        errors: list[str] = []
        for p in self.chains.get(role, []):
            key = f"{p.name}:{p.model}"
            if key == avoid:
                continue
            if self._exhausted.get(key, 0) > time.time():
                errors.append(f"{key}: exhausted")
                continue
            ck = self._cache_key(role, p, system, user)
            if self.use_cache:
                hit = self.db.one("SELECT value FROM llm_cache WHERE key=?", (ck,))
                if hit:
                    try:
                        parsed = out.model_validate_json(hit["value"])
                        res = LLMResult(
                            data=json.loads(hit["value"]),
                            provider=p.name,
                            model=p.model,
                            cached=True,
                        )
                        self._record(role, res, p, True)
                        if role == "generator":
                            self.last_generator = key
                        return parsed, res
                    except ValidationError:
                        pass
            limiter = self._limiter(p)
            attempt = 0
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    limiter.acquire(estimate_tokens(system + user) + 1500)
                    res = p.complete_json(system, user, schema, temperature)
                    parsed = out.model_validate(res.data)
                except QuotaExhausted as e:
                    self._exhausted[key] = time.time() + 3600
                    self._record(role, None, p, False, 429)
                    errors.append(f"{key}: {e}")
                    log.warning("quota exhausted, switching provider: %s", key)
                    break
                except ValidationError as e:
                    self._record(role, None, p, False, 422)
                    errors.append(f"{key}: schema {e.error_count()} errors")
                    if attempt > 2:
                        break
                    continue
                except LLMError as e:
                    self._record(role, None, p, False, e.status)
                    errors.append(f"{key}: {e}")
                    if not e.retryable:
                        break
                    if e.status == 429:
                        limiter.blocked_until = time.time() + (e.retry_after or 2**attempt)
                    delay = (e.retry_after or min(60, 2**attempt)) + random.uniform(0, 1)
                    log.info("retry %s in %.1fs (%s)", key, delay, e)
                    time.sleep(delay)
                    continue
                except Exception as e:  # network errors etc.
                    self._record(role, None, p, False, None)
                    errors.append(f"{key}: {type(e).__name__}: {e}")
                    time.sleep(min(30, 2**attempt))
                    continue
                self._record(role, res, p, True)
                if self.use_cache:
                    self.db.execute(
                        "INSERT OR REPLACE INTO llm_cache(key, value, created_at) VALUES (?,?,?)",
                        (ck, parsed.model_dump_json(), now()),
                    )
                if role == "generator":
                    self.last_generator = key
                return parsed, res
        raise LLMError(f"all providers failed for role={role}: " + " | ".join(errors[-6:]))


def parse_spec(spec: str) -> tuple[str, str]:
    provider, _, model = spec.strip().partition(":")
    return provider.strip(), model.strip()


def build_provider(spec: str, s: Settings) -> LLMProvider | None:
    provider, model = parse_spec(spec)
    try:
        if provider == "gemini":
            return GeminiProvider(model, s.gemini_api_key)
        if provider == "groq":
            return OpenAICompatProvider(
                "groq", model, s.groq_api_key, "https://api.groq.com/openai/v1"
            )
        if provider == "ollama":
            return OllamaProvider(model, s.ollama_url)
    except LLMError as e:
        log.warning("provider %s unavailable: %s", spec, e)
        return None
    log.warning("unknown provider %s", spec)
    return None


def build_router(s: Settings | None = None, db: Database | None = None) -> Router:
    s = s or get_settings()
    if s.local_mode:
        gen = [f"ollama:{s.local_model}"]
        aud = [f"ollama:{s.local_model}"]
    else:
        gen = [s.generator, *[x for x in s.generator_fallbacks.split(",") if x.strip()]]
        aud = [s.auditor, *[x for x in s.auditor_fallbacks.split(",") if x.strip()]]
    chains: dict[str, list[LLMProvider]] = {}
    for role, specs in (("generator", gen), ("auditor", aud)):
        chains[role] = [p for p in (build_provider(x, s) for x in specs) if p is not None]
    budgets = {
        "gemini": Budget(s.gemini_rpm, s.gemini_tpm, s.gemini_rpd),
        "groq": Budget(s.groq_rpm, s.groq_tpm, s.groq_rpd),
        "ollama": Budget(s.ollama_rpm, 10**9, 0),
    }
    return Router(chains, db=db, budgets=budgets)


def describe_chains(router: Router) -> dict[str, list[str]]:
    return {r: [f"{p.name}:{p.model}" for p in ps] for r, ps in router.chains.items()}


__all__ = ["Router", "Budget", "build_router", "describe_chains", "parse_spec", "Any"]
