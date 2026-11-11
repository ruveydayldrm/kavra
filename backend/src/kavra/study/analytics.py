"""Progress analytics: heatmap, streak, topic mastery, weak topics, pipeline quality."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from fsrs import Card

from kavra.db import Database
from kavra.study.scheduler import retrievability


def _local_day(ts: float) -> date:
    return datetime.fromtimestamp(ts).date()


def heatmap(db: Database, days: int = 182) -> list[dict[str, Any]]:
    start = datetime.combine(
        date.today() - timedelta(days=days - 1), datetime.min.time()
    ).timestamp()
    counts: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for r in db.all("SELECT created_at, correct FROM reviews WHERE created_at>=?", (start,)):
        c = counts[_local_day(r["created_at"])]
        c[0] += 1
        c[1] += r["correct"]
    out = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        n, ok = counts.get(d, [0, 0])
        out.append({"date": d.isoformat(), "count": n, "correct": ok})
    return out


def streak(db: Database) -> dict[str, Any]:
    days = {
        _local_day(r["created_at"])
        for r in db.all(
            "SELECT created_at FROM reviews WHERE created_at>=?",
            ((datetime.now() - timedelta(days=400)).timestamp(),),
        )
    }
    today = date.today()
    cur = 0
    d = today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return {"current": cur, "best": best, "studied_today": today in days}


def topic_mastery(db: Database, document_id: int | None = None) -> list[dict[str, Any]]:
    flt = "WHERE t.document_id=?" if document_id else ""
    topics = db.all(
        f"SELECT t.*, d.title AS document_title FROM topics t JOIN documents d ON d.id=t.document_id {flt} ORDER BY t.document_id, t.position",
        [document_id] if document_id else [],
    )
    rows = db.all(
        "SELECT q.id, q.topic_id, c.state FROM questions q JOIN cards c ON c.question_id=q.id WHERE q.status='active'"
    )
    recent = db.all(
        "SELECT q.topic_id, r.correct FROM reviews r JOIN questions q ON q.id=r.question_id ORDER BY r.created_at DESC LIMIT 3000"
    )
    acc: dict[int, list[int]] = defaultdict(list)
    for r in recent:
        if r["topic_id"] is not None and len(acc[r["topic_id"]]) < 30:
            acc[r["topic_id"]].append(r["correct"])
    stats: dict[int, dict[str, Any]] = defaultdict(lambda: {"total": 0, "seen": 0, "r_sum": 0.0})
    for r in rows:
        if r["topic_id"] is None:
            continue
        card = Card.from_dict(json.loads(r["state"]))
        s = stats[r["topic_id"]]
        s["total"] += 1
        if card.last_review is not None:
            s["seen"] += 1
            s["r_sum"] += retrievability(card)
    out = []
    for t in topics:
        s = stats.get(t["id"], {"total": 0, "seen": 0, "r_sum": 0.0})
        a = acc.get(t["id"], [])
        out.append(
            {
                "id": t["id"],
                "document_id": t["document_id"],
                "document_title": t["document_title"],
                "title": t["title"],
                "summary": t["summary"],
                "total": s["total"],
                "seen": s["seen"],
                "mastery": round(s["r_sum"] / s["total"], 3) if s["total"] else 0.0,
                "accuracy": round(sum(a) / len(a), 3) if a else None,
                "attempts": len(a),
            }
        )
    return out


def weak_topics(db: Database, limit: int = 5) -> list[dict[str, Any]]:
    ms = [m for m in topic_mastery(db) if m["attempts"] >= 2 and m["total"]]
    # weakness blends recent accuracy and memory strength
    for m in ms:
        m["weakness"] = round(0.6 * (1 - (m["accuracy"] or 0)) + 0.4 * (1 - m["mastery"]), 3)
    ms.sort(key=lambda m: m["weakness"], reverse=True)
    return [m for m in ms if m["weakness"] > 0.25][:limit]


def quality(db: Database, document_id: int | None = None) -> dict[str, Any]:
    f, p = ("WHERE document_id=?", [document_id]) if document_id else ("", [])
    kept = db.scalar(f"SELECT COUNT(*) FROM questions {f}", p) or 0
    flagged = (
        db.scalar(
            f"SELECT COUNT(*) FROM questions {f + (' AND' if f else 'WHERE')} status='flagged'", p
        )
        or 0
    )
    rej = db.all(f"SELECT stage, COUNT(*) n FROM rejected {f} GROUP BY stage", p)
    rejected = {r["stage"]: r["n"] for r in rej}
    repaired = (
        db.scalar(
            f"SELECT COUNT(*) FROM questions {f + (' AND' if f else 'WHERE')} audit LIKE '%\"repaired\": true%'",
            p,
        )
        or 0
    )
    calls = (
        db.one(
            "SELECT COUNT(*) n, SUM(cached) cached, SUM(tokens_in) tin, SUM(tokens_out) tout FROM llm_calls"
        )
        or {}
    )
    by_provider = db.all(
        "SELECT provider, model, role, COUNT(*) n, SUM(ok) ok FROM llm_calls WHERE cached=0 GROUP BY provider, model, role"
    )
    candidates = (
        kept
        + sum(v for k, v in rejected.items() if k != "duplicate")
        + rejected.get("duplicate", 0)
    )
    return {
        "kept": kept,
        "flagged": flagged,
        "repaired": repaired,
        "rejected": rejected,
        "candidates": candidates,
        "acceptance_rate": round(kept / candidates, 3) if candidates else None,
        "flag_rate": round(flagged / kept, 3) if kept else None,
        "llm_calls": calls.get("n") or 0,
        "cache_hits": calls.get("cached") or 0,
        "tokens": (calls.get("tin") or 0) + (calls.get("tout") or 0),
        "providers": by_provider,
        "cost_usd": 0.0,
    }
