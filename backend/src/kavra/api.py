"""HTTP API (FastAPI). The study endpoints never call an LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from kavra.config import get_settings
from kavra.db import get_db, now
from kavra.ingest import kind_for
from kavra.llm.router import describe_chains
from kavra.service import Service
from kavra.study import analytics, exam, grading, scheduler

log = logging.getLogger("kavra.api")
MAX_UPLOAD = 60 * 1024 * 1024

_service: Service | None = None


def service() -> Service:
    global _service
    if _service is None:
        _service = Service(get_db())
    return _service


def set_service(s: Service | None) -> None:
    global _service
    _service = s


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    svc = service()
    svc.jobs.start()
    yield
    svc.jobs.stop()


app = FastAPI(title="Kavra", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _j(v: Any, default: Any) -> Any:
    if v is None:
        return default
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------------- helpers
def public_question(q: dict[str, Any]) -> dict[str, Any]:
    """What the student sees before answering (no answer, no explanation)."""
    return {
        "id": q["id"],
        "document_id": q["document_id"],
        "topic_id": q["topic_id"],
        "topic": q.get("topic_title"),
        "type": q["type"],
        "difficulty": q["difficulty"],
        "stem": q["stem"],
        "options": _j(q["options"], []),
        "key_point_count": len(_j(q["key_points"], [])),
    }


def full_question(q: dict[str, Any]) -> dict[str, Any]:
    d = public_question(q)
    d.update(
        {
            "correct_index": q["correct_index"],
            "answer": q["answer"],
            "accepted": _j(q["accepted"], []),
            "key_points": _j(q["key_points"], []),
            "explanation": q["explanation"],
            "source": source_of(q),
            "status": q["status"],
            "audit": _j(q["audit"], {}),
            "generator": q["generator"],
            "auditor": q["auditor"],
        }
    )
    return d


def source_of(q: dict[str, Any]) -> dict[str, Any]:
    loc = _j(q["source_loc"], {})
    doc = (
        get_db().one(
            "SELECT id, title, kind, source FROM documents WHERE id=?", (q["document_id"],)
        )
        or {}
    )
    url = None
    if doc.get("kind") == "youtube":
        url = f"{doc['source']}&t={int(loc.get('start', 0))}s"
    elif doc.get("kind") == "pdf":
        url = f"/api/documents/{doc['id']}/file#page={loc.get('page', 1)}"
    elif doc:
        url = f"/api/documents/{doc['id']}/file"
    chunk = (
        get_db().one("SELECT text FROM chunks WHERE id=?", (q["chunk_id"],))
        if q.get("chunk_id")
        else None
    )
    return {
        "quote": q["source_quote"],
        "loc": loc,
        "document": {"id": doc.get("id"), "title": doc.get("title"), "kind": doc.get("kind")},
        "url": url,
        "context": chunk["text"] if chunk else None,
    }


QSELECT = (
    "SELECT q.*, t.title AS topic_title FROM questions q LEFT JOIN topics t ON t.id=q.topic_id"
)


def get_question(qid: int) -> dict[str, Any]:
    q = get_db().one(f"{QSELECT} WHERE q.id=?", (qid,))
    if not q:
        raise HTTPException(404, "question not found")
    return q


def doc_view(d: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    meta = _j(d["meta"], {})
    job = (
        db.one(
            "SELECT id, status, progress, stage, message FROM jobs WHERE id=?",
            (meta.get("job_id"),),
        )
        if meta.get("job_id")
        else None
    )
    return {
        "id": d["id"],
        "title": d["title"],
        "kind": d["kind"],
        "lang": d["lang"],
        "status": d["status"],
        "error": d["error"],
        "created_at": d["created_at"],
        "questions": db.scalar(
            "SELECT COUNT(*) FROM questions WHERE document_id=? AND status='active'", (d["id"],)
        )
        or 0,
        "topics": db.scalar("SELECT COUNT(*) FROM topics WHERE document_id=?", (d["id"],)) or 0,
        "summary": meta.get("summary"),
        "job": job,
        "video_id": meta.get("video_id"),
    }


# ---------------------------------------------------------------------- system
@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_settings()
    svc = service()
    return {
        "ok": True,
        "local_mode": s.local_mode,
        "chains": describe_chains(svc.router),
        "keys": {"gemini": bool(s.gemini_api_key), "groq": bool(s.groq_api_key)},
        "embedder": s.embedder,
    }


# ---------------------------------------------------------------------- documents
@app.get("/api/documents")
def list_documents() -> list[dict[str, Any]]:
    return [doc_view(d) for d in get_db().all("SELECT * FROM documents ORDER BY created_at DESC")]


@app.post("/api/documents", status_code=201)
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    name = file.filename or "upload"
    kind = kind_for(Path(name))
    if not kind:
        raise HTTPException(415, "unsupported file type")
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(name).suffix) as tmp:
        size = 0
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                raise HTTPException(413, "file too large (max 60 MB)")
            tmp.write(chunk)
        tmp_path = Path(tmp.name)
    try:
        return service().add_file(name, tmp_path, kind)
    finally:
        tmp_path.unlink(missing_ok=True)


class YouTubeIn(BaseModel):
    url: str


@app.post("/api/documents/youtube", status_code=201)
def add_youtube(body: YouTubeIn) -> dict[str, Any]:
    try:
        return service().add_youtube(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int) -> dict[str, Any]:
    d = get_db().one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "document not found")
    v = doc_view(d)
    v["topic_list"] = analytics.topic_mastery(get_db(), doc_id)
    v["quality"] = analytics.quality(get_db(), doc_id)
    return v


@app.delete("/api/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int) -> None:
    d = get_db().one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "document not found")
    get_db().execute("DELETE FROM documents WHERE id=?", (doc_id,))
    if d["kind"] != "youtube":
        (get_settings().uploads_dir / d["source"]).unlink(missing_ok=True)


@app.post("/api/documents/{doc_id}/resume")
def resume(doc_id: int) -> dict[str, Any]:
    if not get_db().one("SELECT id FROM documents WHERE id=?", (doc_id,)):
        raise HTTPException(404, "document not found")
    return {"job_id": service().regenerate(doc_id)}


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: int) -> FileResponse:
    d = get_db().one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d or d["kind"] == "youtube":
        raise HTTPException(404, "no file")
    path = (get_settings().uploads_dir / d["source"]).resolve()
    if not path.is_file() or get_settings().uploads_dir.resolve() not in path.parents:
        raise HTTPException(404, "file missing")
    return FileResponse(
        path, filename=path.name.split("_", 1)[-1], content_disposition_type="inline"
    )


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: int) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        last = None
        for _ in range(60 * 60 * 2):  # up to ~1h
            job = get_db().one(
                "SELECT id, status, progress, stage, message FROM jobs WHERE id=?", (job_id,)
            )
            if not job:
                yield "event: error\ndata: {}\n\n"
                return
            payload = json.dumps(job, ensure_ascii=False)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if job["status"] in ("done", "failed"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------- questions
@app.get("/api/questions")
def list_questions(
    document_id: int | None = None, topic_id: int | None = None, status: str = "active"
) -> list[dict[str, Any]]:
    where: list[str] = ["q.status=?"]
    p: list[Any] = [status]
    if document_id:
        where.append("q.document_id=?")
        p.append(document_id)
    if topic_id:
        where.append("q.topic_id=?")
        p.append(topic_id)
    rows = get_db().all(f"{QSELECT} WHERE {' AND '.join(where)} ORDER BY q.id", p)
    return [full_question(q) for q in rows]


@app.get("/api/questions/{qid}")
def question(qid: int) -> dict[str, Any]:
    return full_question(get_question(qid))


class FlagIn(BaseModel):
    reason: Literal["wrong_answer", "ambiguous", "not_in_source", "typo", "other"]
    note: str = Field(default="", max_length=1000)


@app.post("/api/questions/{qid}/flag")
def flag(qid: int, body: FlagIn) -> dict[str, Any]:
    get_question(qid)
    db = get_db()
    db.insert(
        "flags", {"question_id": qid, "reason": body.reason, "note": body.note, "created_at": now()}
    )
    db.execute("UPDATE questions SET status='flagged' WHERE id=?", (qid,))
    return {"ok": True}


@app.post("/api/questions/{qid}/unflag")
def unflag(qid: int) -> dict[str, Any]:
    get_question(qid)
    get_db().execute("UPDATE questions SET status='active' WHERE id=?", (qid,))
    return {"ok": True}


# ---------------------------------------------------------------------- study
@app.get("/api/study/queue")
def study_queue(
    document_id: int | None = None, topic_id: int | None = None, limit: int = Query(30, le=100)
) -> dict[str, Any]:
    db = get_db()
    qd = scheduler.today_queue(db, limit, document_id, topic_id)
    ids = qd["due"] + qd["new"]
    rows = (
        {q["id"]: q for q in db.all(f"{QSELECT} WHERE q.id IN ({','.join('?' * len(ids))})", ids)}
        if ids
        else {}
    )
    items = [{**public_question(rows[i]), "is_new": i in qd["new"]} for i in ids if i in rows]
    return {
        "items": items,
        "due_count": len(qd["due"]),
        "new_count": len(qd["new"]),
        "next_due_at": qd["next_due_at"],
        "new_remaining": qd["new_remaining"],
    }


class CheckIn(BaseModel):
    question_id: int
    response: Any = None
    duration_ms: int | None = None


@app.post("/api/study/check")
def study_check(body: CheckIn) -> dict[str, Any]:
    q = get_question(body.question_id)
    res = grading.check(q, body.response)
    res["suggested_rating"] = grading.auto_rating(res, body.duration_ms, q["type"])
    res["question"] = full_question(q)
    return res


class ReviewIn(BaseModel):
    question_id: int
    rating: int = Field(ge=1, le=4)
    correct: bool
    response: Any = None
    duration_ms: int | None = None
    score: float | None = None


@app.post("/api/study/review")
def study_review(body: ReviewIn) -> dict[str, Any]:
    get_question(body.question_id)
    return scheduler.review(
        get_db(),
        body.question_id,
        body.rating,
        body.correct,
        body.response,
        body.duration_ms,
        body.score,
    )


# ---------------------------------------------------------------------- stats
@app.get("/api/stats/overview")
def overview() -> dict[str, Any]:
    db = get_db()
    q = scheduler.today_queue(db, 500)
    reviewed_today = (
        db.scalar("SELECT COUNT(*) FROM reviews WHERE created_at>=?", (scheduler._day_start(),))
        or 0
    )
    correct_today = (
        db.scalar("SELECT SUM(correct) FROM reviews WHERE created_at>=?", (scheduler._day_start(),))
        or 0
    )
    mastery = analytics.topic_mastery(db)
    return {
        "due": len(q["due"]),
        "new": len(q["new"]),
        "reviewed_today": reviewed_today,
        "correct_today": correct_today,
        "next_due_at": q["next_due_at"],
        "streak": analytics.streak(db),
        "heatmap": analytics.heatmap(db),
        "weak_topics": analytics.weak_topics(db),
        "mastery": mastery,
        "totals": {
            "documents": db.scalar("SELECT COUNT(*) FROM documents") or 0,
            "questions": db.scalar("SELECT COUNT(*) FROM questions WHERE status='active'") or 0,
            "reviews": db.scalar("SELECT COUNT(*) FROM reviews") or 0,
        },
    }


@app.get("/api/stats/quality")
def quality(document_id: int | None = None) -> dict[str, Any]:
    return analytics.quality(get_db(), document_id)


# ---------------------------------------------------------------------- exams
class ExamIn(BaseModel):
    count: int = Field(20, ge=3, le=100)
    minutes: int = Field(20, ge=1, le=240)
    document_ids: list[int] | None = None
    types: list[Literal["mcq", "tf", "cloze", "open"]] | None = None


@app.post("/api/exams", status_code=201)
def new_exam(body: ExamIn) -> dict[str, Any]:
    try:
        e = exam.create_exam(
            get_db(),
            body.count,
            body.minutes,
            body.document_ids,
            list(body.types) if body.types else None,
        )
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    ids = e["question_ids"]
    rows = {
        q["id"]: q
        for q in get_db().all(f"{QSELECT} WHERE q.id IN ({','.join('?' * len(ids))})", ids)
    }
    e["questions"] = [public_question(rows[i]) for i in ids]
    return e


class SubmitIn(BaseModel):
    answers: dict[str, Any]


@app.post("/api/exams/{exam_id}/submit")
def submit(exam_id: int, body: SubmitIn) -> dict[str, Any]:
    try:
        report = exam.submit_exam(get_db(), exam_id, body.answers)
    except ValueError as err:
        raise HTTPException(404, str(err)) from err
    ids = [it["question_id"] for it in report["items"]]
    rows = (
        {
            q["id"]: q
            for q in get_db().all(f"{QSELECT} WHERE q.id IN ({','.join('?' * len(ids))})", ids)
        }
        if ids
        else {}
    )
    for it in report["items"]:
        if it["question_id"] in rows:
            it["question"] = full_question(rows[it["question_id"]])
    return report


@app.get("/api/exams")
def exams() -> list[dict[str, Any]]:
    out = []
    for e in get_db().all(
        "SELECT id, title, minutes, started_at, finished_at, report FROM exams ORDER BY id DESC LIMIT 30"
    ):
        r = _j(e.pop("report"), None)
        e["ratio"] = r["ratio"] if r else None
        e["total"] = r["total"] if r else None
        out.append(e)
    return out
