import pytest
from pydantic import BaseModel

from kavra.db import Database
from kavra.llm import Budget, FakeProvider, LLMError, QuotaExhausted, Router, strict_schema


class Out(BaseModel):
    word: str
    n: int


def test_strict_schema_inlines_refs_and_requires_all():
    from kavra.pipeline.schemas import AuditReport

    s = strict_schema(AuditReport)
    assert "$defs" not in str(s)
    item = s["properties"]["items"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


def test_fallback_on_quota_and_cache(db: Database):
    def dead(*_):
        raise QuotaExhausted("daily", 429)

    a = FakeProvider(dead, name="a")
    b = FakeProvider(lambda *_: {"word": "ok", "n": 1}, name="b")
    r = Router({"generator": [a, b]}, db=db)
    out, res = r.call("generator", "s", "u", Out)
    assert out.word == "ok" and res.provider == "b"
    # second call: a is marked exhausted (skipped), b answers from cache
    out, res = r.call("generator", "s", "u", Out)
    assert res.cached and len(b.calls) == 1 and len(a.calls) == 1


def test_retry_then_success(db: Database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    n = {"i": 0}

    def flaky(*_):
        n["i"] += 1
        if n["i"] < 3:
            raise LLMError("busy", 503, retry_after=0)
        return {"word": "x", "n": 2}

    r = Router({"generator": [FakeProvider(flaky)]}, db=db, use_cache=False)
    out, _ = r.call("generator", "s", "u", Out)
    assert out.n == 2 and n["i"] == 3


def test_schema_violation_falls_through(db: Database):
    bad = FakeProvider(lambda *_: {"word": "x"}, name="bad")
    good = FakeProvider(lambda *_: {"word": "y", "n": 3}, name="good")
    r = Router({"generator": [bad, good]}, db=db, use_cache=False)
    out, res = r.call("generator", "s", "u", Out)
    assert res.provider == "good"


def test_all_fail_raises(db: Database):
    def dead(*_):
        raise LLMError("unauthorized", 401)

    r = Router({"generator": [FakeProvider(dead)]}, db=db)
    with pytest.raises(LLMError):
        r.call("generator", "s", "u", Out)


def test_local_daily_budget(db: Database):
    p = FakeProvider(lambda *_: {"word": "x", "n": 1}, name="lim")
    r = Router(
        {"generator": [p]},
        db=db,
        budgets={"lim": Budget(rpm=100, tpm=10**9, rpd=1)},
        use_cache=False,
    )
    r.call("generator", "s", "u1", Out)
    with pytest.raises(LLMError):
        r.call("generator", "s", "u2", Out)
