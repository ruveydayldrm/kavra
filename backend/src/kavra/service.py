"""Glue between the API, ingestion, the pipeline and the job queue."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from kavra.config import Settings, get_settings
from kavra.db import Database, now
from kavra.ingest import build_chunks, detect_lang, extract, youtube
from kavra.jobs import JobQueue
from kavra.llm.router import Router, build_router
from kavra.pipeline.run import Pipeline

log = logging.getLogger("kavra.service")


def safe_name(name: str) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("._") or "file"
    return stem[:120]


class Service:
    def __init__(
        self, db: Database, settings: Settings | None = None, router: Router | None = None
    ):
        self.db = db
        self.s = settings or get_settings()
        self._router = router
        self.jobs = JobQueue(db)
        self.jobs.register("ingest", self._job_ingest)
        self.jobs.register("generate", self._job_generate)

    @property
    def router(self) -> Router:
        if self._router is None:
            self._router = build_router(self.s, self.db)
        return self._router

    def reload_router(self) -> None:
        self._router = None

    # ---- documents ------------------------------------------------------
    def add_file(
        self, filename: str, src: Path, kind: str, title: str | None = None
    ) -> dict[str, Any]:
        stored = f"{int(now() * 1000)}_{safe_name(filename)}"
        dest = self.s.uploads_dir / stored
        shutil.copyfile(src, dest)
        doc_id = self.db.insert(
            "documents",
            {
                "title": title or Path(filename).stem.replace("_", " "),
                "kind": kind,
                "source": stored,
                "status": "queued",
                "created_at": now(),
            },
        )
        job = self.jobs.enqueue("ingest", {"document_id": doc_id})
        self.db.execute(
            "UPDATE documents SET meta=? WHERE id=?", (json.dumps({"job_id": job}), doc_id)
        )
        return {"id": doc_id, "job_id": job}

    def add_youtube(self, url: str) -> dict[str, Any]:
        vid = youtube.video_id(url)
        if not vid:
            raise ValueError("invalid YouTube URL")
        doc_id = self.db.insert(
            "documents",
            {
                "title": f"YouTube · {vid}",
                "kind": "youtube",
                "source": f"https://www.youtube.com/watch?v={vid}",
                "status": "queued",
                "created_at": now(),
            },
        )
        job = self.jobs.enqueue("ingest", {"document_id": doc_id})
        self.db.execute(
            "UPDATE documents SET meta=? WHERE id=?",
            (json.dumps({"job_id": job, "video_id": vid}), doc_id),
        )
        return {"id": doc_id, "job_id": job}

    def regenerate(self, doc_id: int) -> int:
        job = self.jobs.enqueue("generate", {"document_id": doc_id})
        meta = json.loads(
            (self.db.one("SELECT meta FROM documents WHERE id=?", (doc_id,)) or {"meta": "{}"})[
                "meta"
            ]
        )
        meta["job_id"] = job
        self.db.execute(
            "UPDATE documents SET meta=?, status='queued' WHERE id=?", (json.dumps(meta), doc_id)
        )
        return job

    # ---- jobs -------------------------------------------------------------
    def ingest_document(self, doc_id: int, progress: Any = None) -> int:
        progress = progress or (lambda p, s, m="": None)
        doc = self.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
        if not doc:
            raise ValueError("document not found")
        if self.db.scalar("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)):
            return int(self.db.scalar("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)))
        progress(0.01, "extract", "")
        if doc["kind"] == "youtube":
            title, lang, segs = youtube.fetch(doc["source"])
            self.db.execute("UPDATE documents SET title=? WHERE id=?", (title, doc_id))
        else:
            segs = extract(self.s.uploads_dir / doc["source"], doc["kind"])
            lang = detect_lang(" ".join(s.text for s in segs[:200]))
        if not segs:
            raise ValueError("no text could be extracted")
        chunks = build_chunks(segs, self.s.chunk_chars)
        with self.db.tx() as c:
            for ch in chunks:
                c.execute(
                    "INSERT INTO chunks(document_id, idx, text, segments) VALUES (?,?,?,?)",
                    (doc_id, ch.idx, ch.text, json.dumps(ch.segments, ensure_ascii=False)),
                )
            c.execute("UPDATE documents SET lang=? WHERE id=?", (lang, doc_id))
        progress(0.04, "chunks", f"{len(chunks)}")
        return len(chunks)

    def _job_ingest(self, payload: dict[str, Any], progress: Any) -> None:
        doc_id = payload["document_id"]
        self.db.execute(
            "UPDATE documents SET status='processing', error=NULL WHERE id=?", (doc_id,)
        )
        try:
            self.ingest_document(doc_id, progress)
        except Exception as e:
            self.db.execute(
                "UPDATE documents SET status='failed', error=? WHERE id=?", (str(e)[:500], doc_id)
            )
            raise
        self._job_generate(payload, progress)

    def _job_generate(self, payload: dict[str, Any], progress: Any) -> None:
        doc_id = payload["document_id"]
        self.db.execute(
            "UPDATE documents SET status='processing', error=NULL WHERE id=?", (doc_id,)
        )
        try:
            summary = Pipeline(self.db, self.router, self.s).run(doc_id, progress)
        except Exception as e:
            self.db.execute(
                "UPDATE documents SET status='failed', error=? WHERE id=?", (str(e)[:500], doc_id)
            )
            raise
        status = "ready" if not summary["remaining_chunks"] else "partial"
        err = None if status == "ready" else ("; ".join(summary["errors"]) or "rate limited")[:500]
        meta = json.loads(
            (self.db.one("SELECT meta FROM documents WHERE id=?", (doc_id,)) or {"meta": "{}"})[
                "meta"
            ]
        )
        meta["summary"] = summary
        self.db.execute(
            "UPDATE documents SET status=?, error=?, meta=? WHERE id=?",
            (status, err, json.dumps(meta, ensure_ascii=False), doc_id),
        )
