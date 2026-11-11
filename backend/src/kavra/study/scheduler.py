"""FSRS spaced repetition (py-fsrs). Pure algorithm — no model calls while studying."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fsrs import Card, Rating, Scheduler

from kavra.config import get_settings
from kavra.db import Database, now

_scheduler: Scheduler | None = None


def scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(desired_retention=get_settings().desired_retention)
    return _scheduler


def ensure_card(db: Database, qid: int) -> None:
    card = Card()
    db.execute(
        "INSERT OR IGNORE INTO cards(question_id, state, due, introduced_at) VALUES (?,?,?,NULL)",
        (qid, json.dumps(card.to_dict()), now()),
    )


def load_card(db: Database, qid: int) -> Card:
    row = db.one("SELECT state FROM cards WHERE question_id=?", (qid,))
    if not row:
        ensure_card(db, qid)
        return Card()
    return Card.from_dict(json.loads(row["state"]))


def retrievability(card: Card, at: datetime | None = None) -> float:
    if card.last_review is None:
        return 0.0
    return float(scheduler().get_card_retrievability(card, at or datetime.now(UTC)))


def _day_start() -> float:
    lt = datetime.now().astimezone()
    return lt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


ACTIVE = "q.status='active'"


def today_queue(
    db: Database, limit: int = 40, document_id: int | None = None, topic_id: int | None = None
) -> dict[str, Any]:
    flt, params = "", []
    if document_id:
        flt += " AND q.document_id=?"
        params.append(document_id)
    if topic_id:
        flt += " AND q.topic_id=?"
        params.append(topic_id)
    t = now()
    due = db.all(
        f"SELECT q.id FROM cards c JOIN questions q ON q.id=c.question_id WHERE {ACTIVE} AND c.introduced_at IS NOT NULL AND c.due<=? {flt} ORDER BY c.due LIMIT ?",
        [t, *params, limit],
    )
    introduced_today = (
        db.scalar("SELECT COUNT(*) FROM cards WHERE introduced_at>=?", (_day_start(),)) or 0
    )
    new_budget = max(0, get_settings().new_cards_per_day - int(introduced_today))
    if topic_id:
        new_budget = max(new_budget, 10)  # focused practice on a topic always has material
    new_budget = min(new_budget, max(0, limit - len(due)))
    # new cards: weakest topics first, then document order, easy before hard
    new = db.all(
        f"""SELECT q.id FROM cards c JOIN questions q ON q.id=c.question_id
            LEFT JOIN topics tp ON tp.id=q.topic_id
            WHERE {ACTIVE} AND c.introduced_at IS NULL {flt}
            ORDER BY q.document_id, tp.position,
              CASE q.difficulty WHEN 'easy' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, q.id
            LIMIT ?""",
        [*params, new_budget],
    )
    later = db.scalar(
        f"SELECT MIN(c.due) FROM cards c JOIN questions q ON q.id=c.question_id WHERE {ACTIVE} AND c.introduced_at IS NOT NULL AND c.due>? {flt}",
        [t, *params],
    )
    total_new = db.scalar(
        f"SELECT COUNT(*) FROM cards c JOIN questions q ON q.id=c.question_id WHERE {ACTIVE} AND c.introduced_at IS NULL {flt}",
        params,
    )
    return {
        "due": [r["id"] for r in due],
        "new": [r["id"] for r in new],
        "next_due_at": later,
        "new_remaining": int(total_new or 0),
    }


RATINGS = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}


def review(
    db: Database,
    qid: int,
    rating: int,
    correct: bool,
    response: Any = None,
    duration_ms: int | None = None,
    score: float | None = None,
    mode: str = "study",
) -> dict[str, Any]:
    card = load_card(db, qid)
    r_before = retrievability(card)
    new_card, _ = scheduler().review_card(card, RATINGS[rating], review_duration=duration_ms)
    due_ts = new_card.due.timestamp()
    with db.tx() as c:
        c.execute(
            "UPDATE cards SET state=?, due=?, introduced_at=COALESCE(introduced_at, ?) WHERE question_id=?",
            (json.dumps(new_card.to_dict()), due_ts, now(), qid),
        )
        c.execute(
            "INSERT INTO reviews(question_id, rating, correct, score, response, duration_ms, mode, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                qid,
                rating,
                int(correct),
                score,
                json.dumps(response, ensure_ascii=False),
                duration_ms,
                mode,
                now(),
            ),
        )
    return {"due": due_ts, "stability": new_card.stability, "retrievability_before": r_before}
