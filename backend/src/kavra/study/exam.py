"""Timed mixed exams with a per-topic report."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from typing import Any

from kavra.db import Database, now
from kavra.study.grading import check


def create_exam(
    db: Database,
    count: int = 20,
    minutes: int = 20,
    document_ids: list[int] | None = None,
    types: list[str] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    where: list[str] = ["status='active'"]
    params: list[Any] = []
    if document_ids:
        where.append(f"document_id IN ({','.join('?' * len(document_ids))})")
        params += document_ids
    if types:
        where.append(f"type IN ({','.join('?' * len(types))})")
        params += types
    rows = db.all(
        f"SELECT id, topic_id, difficulty FROM questions WHERE {' AND '.join(where)}", params
    )
    if not rows:
        raise ValueError("no questions available")
    by_topic: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_topic[r["topic_id"]].append(r)
    for lst in by_topic.values():
        rng.shuffle(lst)
    # round-robin across topics => balanced coverage
    picked: list[int] = []
    pools = list(by_topic.values())
    rng.shuffle(pools)
    while len(picked) < min(count, len(rows)):
        for pool in pools:
            if pool and len(picked) < count:
                picked.append(pool.pop()["id"])
    rng.shuffle(picked)
    title = f"Sınav · {len(picked)} soru"
    eid = db.insert(
        "exams", {"title": title, "question_ids": picked, "minutes": minutes, "started_at": now()}
    )
    return {
        "id": eid,
        "title": title,
        "question_ids": picked,
        "minutes": minutes,
        "started_at": now(),
    }


def submit_exam(db: Database, exam_id: int, answers: dict[str, Any]) -> dict[str, Any]:
    exam = db.one("SELECT * FROM exams WHERE id=?", (exam_id,))
    if not exam:
        raise ValueError("exam not found")
    if exam["report"]:
        return json.loads(exam["report"])
    qids: list[int] = json.loads(exam["question_ids"])
    qs = {
        q["id"]: q
        for q in db.all(
            f"SELECT q.*, t.title AS topic_title FROM questions q LEFT JOIN topics t ON t.id=q.topic_id WHERE q.id IN ({','.join('?' * len(qids))})",
            qids,
        )
    }
    per_topic: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "score": 0.0})
    items = []
    total = 0.0
    for qid in qids:
        q = qs.get(qid)
        if not q:
            continue
        resp = answers.get(str(qid))
        res = (
            check(q, resp)
            if resp not in (None, "")
            else {"correct": False, "score": 0.0, "skipped": True}
        )
        sc = float(res.get("score", 0.0))
        total += sc
        t = per_topic[q["topic_title"] or "—"]
        t["total"] += 1
        t["score"] += sc
        items.append({"question_id": qid, "response": resp, **res})
        with db.tx() as c:
            c.execute(
                "INSERT INTO reviews(question_id, rating, correct, score, response, duration_ms, mode, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    qid,
                    3 if res["correct"] else 1,
                    int(res["correct"]),
                    sc,
                    json.dumps(resp, ensure_ascii=False),
                    None,
                    "exam",
                    now(),
                ),
            )
    topics = sorted(
        (
            {
                "topic": k,
                "total": v["total"],
                "score": round(v["score"], 2),
                "ratio": round(v["score"] / v["total"], 3),
            }
            for k, v in per_topic.items()
        ),
        key=lambda x: x["ratio"],
    )
    report = {
        "exam_id": exam_id,
        "score": round(total, 2),
        "total": len(items),
        "ratio": round(total / len(items), 3) if items else 0.0,
        "elapsed_s": round(now() - exam["started_at"]),
        "minutes": exam["minutes"],
        "topics": topics,
        "items": items,
    }
    db.execute(
        "UPDATE exams SET finished_at=?, report=? WHERE id=?",
        (now(), json.dumps(report, ensure_ascii=False), exam_id),
    )
    return report
