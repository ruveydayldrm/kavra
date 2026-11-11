"""SQLite (WAL) storage. One connection per thread, small helper API."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,             -- pdf | pptx | docx | image | youtube | text
  source TEXT NOT NULL,           -- stored file name or URL
  lang TEXT NOT NULL DEFAULT 'tr',
  status TEXT NOT NULL DEFAULT 'queued',  -- queued | processing | ready | failed
  error TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  text TEXT NOT NULL,
  segments TEXT NOT NULL,         -- JSON [{start,end,loc:{...}}] char offsets -> locator
  topic_id INTEGER,
  processed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  misconceptions TEXT NOT NULL DEFAULT '[]',
  position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
  chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  stem TEXT NOT NULL,
  options TEXT NOT NULL DEFAULT '[]',
  correct_index INTEGER NOT NULL DEFAULT -1,
  answer TEXT NOT NULL,
  accepted TEXT NOT NULL DEFAULT '[]',
  key_points TEXT NOT NULL DEFAULT '[]',
  explanation TEXT NOT NULL,
  source_quote TEXT NOT NULL,
  source_loc TEXT NOT NULL,       -- JSON locator
  status TEXT NOT NULL DEFAULT 'active',  -- active | flagged | dropped
  audit TEXT NOT NULL DEFAULT '{}',
  generator TEXT NOT NULL DEFAULT '',
  auditor TEXT NOT NULL DEFAULT '',
  embedding BLOB,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,            -- schema | quote | audit | duplicate | repair
  reason TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
  question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
  state TEXT NOT NULL,            -- fsrs Card JSON
  due REAL NOT NULL,
  introduced_at REAL
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL,
  correct INTEGER NOT NULL,
  score REAL,
  response TEXT,
  duration_ms INTEGER,
  mode TEXT NOT NULL DEFAULT 'study',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS flags (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS exams (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  question_ids TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  started_at REAL NOT NULL,
  finished_at REAL,
  report TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed
  progress REAL NOT NULL DEFAULT 0,
  stage TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  role TEXT NOT NULL,
  ok INTEGER NOT NULL,
  status INTEGER,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  cached INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_q_doc ON questions(document_id, status);
CREATE INDEX IF NOT EXISTS ix_cards_due ON cards(due);
CREATE INDEX IF NOT EXISTS ix_reviews_time ON reviews(created_at);
CREATE INDEX IF NOT EXISTS ix_calls ON llm_calls(provider, model, created_at);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        with self.tx() as c:
            c.executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            if self.path != ":memory:":
                c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            c = self.conn()
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        row = self.conn().execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn().execute(sql, tuple(params)).fetchall()]

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.conn().execute(sql, tuple(params)).fetchone()
        return row[0] if row else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.tx() as c:
            cur = c.execute(sql, tuple(params))
            return int(cur.lastrowid or 0)

    def insert(self, table: str, data: dict[str, Any]) -> int:
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        vals = [
            json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v
            for v in data.values()
        ]
        return self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", vals)


def now() -> float:
    return time.time()


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    with _db_lock:
        if _db is None:
            from kavra.config import get_settings

            _db = Database(get_settings().db_path)
        return _db


def set_db(db: Database | None) -> None:
    global _db
    _db = db
