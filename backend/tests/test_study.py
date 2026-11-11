import json
from pathlib import Path

from test_pipeline import _ingest

from kavra.db import Database
from kavra.llm import Router
from kavra.pipeline.run import Pipeline
from kavra.study import analytics, exam, grading, scheduler


def _q(**kw):
    base = {
        "type": "cloze",
        "answer": "mitokondri",
        "accepted": json.dumps(["mitokondrion"]),
        "key_points": "[]",
        "correct_index": -1,
    }
    base.update(kw)
    return base


def test_cloze_grading_tolerates_suffix_and_typos():
    assert grading.check(_q(), "Mitokondri")["correct"]
    assert grading.check(_q(), "mitokondride")["correct"]
    assert grading.check(_q(), "mitokondiri")["correct"]
    assert not grading.check(_q(), "kloroplast")["correct"]


def test_tf_and_mcq():
    assert grading.check({"type": "tf", "answer": "false"}, "false")["correct"]
    assert not grading.check({"type": "tf", "answer": "true"}, "false")["correct"]
    assert grading.check({"type": "mcq", "correct_index": 2}, 2)["correct"]


def test_open_grading_finds_missing_points(db: Database):
    kps = ["Glikoliz sitoplazmada gerçekleşir", "Glikoliz oksijen gerektirmez"]
    r = grading.check(
        {"type": "open", "key_points": json.dumps(kps)},
        "Glikoliz sitoplazmada gerçekleşen bir süreçtir.",
    )
    assert r["covered"] == [0] and r["missing"] == [1]
    full = grading.check(
        {"type": "open", "key_points": json.dumps(kps)},
        "Glikoliz sitoplazmada olur ve oksijen gerektirmez.",
    )
    assert full["correct"] and full["score"] == 1.0


def test_fsrs_queue_and_review(db: Database, router: Router, tmp_path: Path):
    doc_id = _ingest(db, router, tmp_path)
    Pipeline(db, router).run(doc_id)
    q = scheduler.today_queue(db)
    assert not q["due"] and q["new"]
    qid = q["new"][0]
    r = scheduler.review(db, qid, 3, True)
    assert r["due"] > 0
    q2 = scheduler.today_queue(db)
    assert qid not in q2["new"]
    scheduler.review(db, q["new"][1], 1, False)
    assert analytics.streak(db)["current"] == 1
    hm = analytics.heatmap(db)
    assert hm[-1]["count"] == 2 and hm[-1]["correct"] == 1
    m = analytics.topic_mastery(db)
    assert any(t["seen"] for t in m)


def test_exam_balances_topics_and_reports(db: Database, router: Router, tmp_path: Path):
    doc_id = _ingest(db, router, tmp_path)
    Pipeline(db, router).run(doc_id)
    e = exam.create_exam(db, count=4, minutes=5, seed=1)
    qs = db.all(
        f"SELECT * FROM questions WHERE id IN ({','.join('?' * len(e['question_ids']))})",
        e["question_ids"],
    )
    assert len({q["topic_id"] for q in qs}) == 2
    answers = {str(q["id"]): q["correct_index"] for q in qs[:2]}
    rep = exam.submit_exam(db, e["id"], answers)
    assert rep["total"] == len(qs) and rep["score"] == 2
    assert {t["topic"] for t in rep["topics"]} == {"Fotosentez", "Solunum"}
    q = analytics.quality(db)
    assert q["cost_usd"] == 0.0 and q["kept"] > 0
