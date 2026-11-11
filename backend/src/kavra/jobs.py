"""Background job queue.

Windows-friendly: a single worker thread pulling from the `jobs` table (so jobs survive a
restart). LLM throughput is bounded by free-tier rate limits anyway, so one worker is the
right amount of parallelism. Progress lives in the DB and is streamed to the UI via SSE.
"""

from __future__ import annotations

import json
import logging
import threading
import traceback
from collections.abc import Callable
from typing import Any

from kavra.db import Database, now

log = logging.getLogger("kavra.jobs")
Handler = Callable[[dict[str, Any], Callable[[float, str, str], None]], Any]


class JobQueue:
    def __init__(self, db: Database):
        self.db = db
        self.handlers: dict[str, Handler] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, kind: str, handler: Handler) -> None:
        self.handlers[kind] = handler

    def enqueue(self, kind: str, payload: dict[str, Any]) -> int:
        jid = self.db.insert(
            "jobs", {"kind": kind, "payload": payload, "created_at": now(), "updated_at": now()}
        )
        self._wake.set()
        return jid

    def update(self, jid: int, **fields: Any) -> None:
        fields["updated_at"] = now()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*fields.values(), jid])

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        # crash recovery: anything left running is re-queued
        self.db.execute("UPDATE jobs SET status='queued' WHERE status='running'")
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="kavra-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run_next(self) -> bool:
        job = self.db.one("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1")
        if not job:
            return False
        jid = job["id"]
        self.update(jid, status="running", stage="start", progress=0.0)
        handler = self.handlers.get(job["kind"])

        def progress(p: float, stage: str, message: str = "") -> None:
            self.update(
                jid, progress=round(min(1.0, max(0.0, p)), 3), stage=stage, message=message[:2000]
            )

        try:
            if handler is None:
                raise RuntimeError(f"no handler for {job['kind']}")
            handler(json.loads(job["payload"]), progress)
            self.update(jid, status="done", progress=1.0)
        except Exception as e:
            log.error("job %s failed: %s\n%s", jid, e, traceback.format_exc())
            self.update(jid, status="failed", message=f"{type(e).__name__}: {e}"[:2000])
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_next()
            except Exception:  # never let the worker die
                log.exception("job loop error")
                worked = False
            if not worked:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
