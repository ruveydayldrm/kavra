from pathlib import Path

from conftest import NOTES
from fastapi.testclient import TestClient

from kavra import api
from kavra.db import Database
from kavra.llm import Router
from kavra.service import Service


def test_upload_study_flag_exam(db: Database, router: Router, tmp_path: Path):
    svc = Service(db, router=router)
    svc.s.chunk_chars = 260
    api.set_service(svc)
    client = TestClient(api.app)

    r = client.post(
        "/api/documents", files={"file": ("biyo.txt", NOTES.encode("utf-8"), "text/plain")}
    )
    assert r.status_code == 201
    doc_id = r.json()["id"]
    while svc.jobs.run_next():
        pass
    d = client.get(f"/api/documents/{doc_id}").json()
    assert d["status"] == "ready" and d["questions"] > 0 and len(d["topic_list"]) == 2

    q = client.get("/api/study/queue").json()
    item = q["items"][0]
    assert "answer" not in item and "explanation" not in item
    chk = client.post(
        "/api/study/check", json={"question_id": item["id"], "response": 0, "duration_ms": 3000}
    ).json()
    assert chk["correct"] and chk["question"]["source"]["quote"]
    assert chk["question"]["source"]["loc"]["kind"] == "page"
    rv = client.post(
        "/api/study/review",
        json={"question_id": item["id"], "rating": chk["suggested_rating"], "correct": True},
    )
    assert rv.status_code == 200

    assert client.post(f"/api/questions/{item['id']}/flag", json={"reason": "ambiguous"}).json()[
        "ok"
    ]
    assert all(i["id"] != item["id"] for i in client.get("/api/study/queue").json()["items"])

    ov = client.get("/api/stats/overview").json()
    assert ov["reviewed_today"] == 1 and ov["streak"]["current"] == 1

    e = client.post("/api/exams", json={"count": 3, "minutes": 5}).json()
    active = db.scalar("SELECT COUNT(*) FROM questions WHERE status='active'")
    assert len(e["questions"]) == min(3, active)  # flagged questions never appear in exams
    rep = client.post(f"/api/exams/{e['id']}/submit", json={"answers": {}}).json()
    assert rep["score"] == 0 and rep["items"][0]["question"]["explanation"]

    assert client.get("/api/stats/quality").json()["flagged"] == 1
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    api.set_service(None)


def test_rejects_unknown_file_type(db: Database, router: Router):
    api.set_service(Service(db, router=router))
    client = TestClient(api.app)
    r = client.post("/api/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415
    api.set_service(None)
