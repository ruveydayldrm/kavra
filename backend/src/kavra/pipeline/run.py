"""The generation pipeline for one document.

    chunks -> topic map -> per chunk: generate -> code checks (schema, verbatim quote)
           -> audit by a *different* model -> repair (once) or drop -> dedup -> store

Everything is idempotent: finished chunks are skipped and LLM calls hit the cache, so a run
interrupted by a rate limit resumes where it stopped.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from kavra.config import Settings, get_settings
from kavra.db import Database, now
from kavra.embed import Embedder, from_blob, get_embedder, to_blob
from kavra.ingest import Chunk
from kavra.llm.base import LLMError
from kavra.llm.router import Router
from kavra.pipeline import prompts
from kavra.pipeline.schemas import AuditItem, AuditReport, QuestionBatch, QuestionDraft, TopicMap
from kavra.pipeline.verify import locate_quote, structural_issues

log = logging.getLogger("kavra.pipeline")
Progress = Callable[[float, str, str], None]


@dataclass
class ChunkStats:
    generated: int = 0
    kept: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    repaired: int = 0

    def reject(self, stage: str) -> None:
        self.rejected[stage] = self.rejected.get(stage, 0) + 1


def _chunk_obj(row: dict[str, Any]) -> Chunk:
    return Chunk(idx=row["idx"], text=row["text"], segments=json.loads(row["segments"]))


class Pipeline:
    def __init__(
        self,
        db: Database,
        router: Router,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
    ):
        self.db = db
        self.router = router
        self.s = settings or get_settings()
        self.embedder = embedder or get_embedder()

    # ------------------------------------------------------------------ topics
    def build_topics(self, doc: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
        if self.db.scalar("SELECT COUNT(*) FROM topics WHERE document_id=?", (doc["id"],)):
            return
        lang = prompts.lang_name(doc["lang"])
        ids = [c["id"] for c in chunks]
        topics: list[dict[str, Any]] = []
        try:
            tm, _ = self.router.call(
                "generator",
                prompts.TOPIC_SYSTEM.format(lang=lang),
                prompts.topic_user([(c["id"], c["text"]) for c in chunks], doc["title"]),
                TopicMap,
                temperature=0.2,
            )
            seen: set[int] = set()
            for draft in tm.topics:
                cids = [c for c in draft.chunk_ids if c in ids and c not in seen]
                seen.update(cids)
                if draft.title.strip():
                    topics.append(
                        {
                            "title": draft.title.strip(),
                            "summary": draft.summary,
                            "misc": draft.misconceptions,
                            "cids": cids,
                        }
                    )
        except LLMError as e:
            log.warning("topic map failed, using a single topic: %s", e)
        if not topics:
            topics = [{"title": doc["title"], "summary": "", "misc": [], "cids": ids}]
        # assign orphan chunks to the most similar topic
        assigned = {c for t in topics for c in t["cids"]}
        orphans = [c for c in chunks if c["id"] not in assigned]
        if orphans:
            tv = self.embedder.encode([t["title"] + ". " + t["summary"] for t in topics])
            ov = self.embedder.encode([c["text"][:600] for c in orphans])
            best = (ov @ tv.T).argmax(axis=1)
            for c, b in zip(orphans, best, strict=True):
                topics[int(b)]["cids"].append(c["id"])
        for pos, t in enumerate(topics):
            if not t["cids"]:
                continue
            tid = self.db.insert(
                "topics",
                {
                    "document_id": doc["id"],
                    "title": t["title"],
                    "summary": t["summary"],
                    "misconceptions": t["misc"],
                    "position": pos,
                },
            )
            self.db.execute(
                f"UPDATE chunks SET topic_id=? WHERE id IN ({','.join('?' * len(t['cids']))})",
                [tid, *t["cids"]],
            )

    # --------------------------------------------------------------- generate
    def _reject(
        self, doc_id: int, stage: str, reason: str, payload: Any, stats: ChunkStats
    ) -> None:
        stats.reject(stage)
        self.db.insert(
            "rejected",
            {
                "document_id": doc_id,
                "stage": stage,
                "reason": reason[:500],
                "payload": payload if isinstance(payload, dict | list) else {"v": str(payload)},
                "created_at": now(),
            },
        )

    def _code_check(
        self, q: QuestionDraft, chunk: Chunk, doc_id: int, stats: ChunkStats
    ) -> tuple[QuestionDraft, dict[str, Any]] | None:
        q, issues = structural_issues(q, chunk.text)
        if issues:
            self._reject(doc_id, "schema", "; ".join(issues), q.model_dump(), stats)
            return None
        m = locate_quote(chunk.text, q.source_quote, self.s.quote_match_threshold)
        if m is None:
            self._reject(
                doc_id, "quote", "source_quote not found in excerpt", q.model_dump(), stats
            )
            return None
        loc = chunk.locate(m.start, m.end)
        loc["quote_score"] = round(m.score, 1)
        # store the excerpt's exact wording, not the model's paraphrase
        q.source_quote = chunk.text[m.start : m.end]
        return q, loc

    def _audit(self, chunk: Chunk, qs: list[QuestionDraft], lang: str) -> list[AuditItem] | None:
        if self.s.single_model or not qs:
            return None
        report, res = self.router.call(
            "auditor",
            prompts.AUDIT_SYSTEM.format(lang=lang),
            prompts.audit_user(chunk.text, [q.model_dump() for q in qs]),
            AuditReport,
            temperature=0.0,
            avoid=self.router.last_generator,
        )
        self._last_auditor = f"{res.provider}:{res.model}"
        by_idx = {it.index: it for it in report.items}
        return [by_idx.get(i) or _missing_audit(i) for i in range(len(qs))]

    def process_chunk(
        self, doc: dict[str, Any], row: dict[str, Any], topic: dict[str, Any] | None
    ) -> ChunkStats:
        stats = ChunkStats()
        chunk = _chunk_obj(row)
        lang = prompts.lang_name(doc["lang"])
        existing = self.db.all(
            "SELECT stem FROM questions WHERE document_id=? AND topic_id IS ? AND status='active' ORDER BY id DESC LIMIT 12",
            (doc["id"], row["topic_id"]),
        )
        batch, gres = self.router.call(
            "generator",
            prompts.GEN_SYSTEM.format(lang=lang),
            prompts.gen_user(
                chunk.text,
                topic["title"] if topic else doc["title"],
                json.loads(topic["misconceptions"]) if topic else [],
                self.s.questions_per_chunk,
                [e["stem"] for e in existing],
            ),
            QuestionBatch,
            temperature=0.6,
        )
        generator = f"{gres.provider}:{gres.model}"
        stats.generated = len(batch.questions)
        checked: list[tuple[QuestionDraft, dict[str, Any]]] = []
        for q in batch.questions:
            r = self._code_check(q, chunk, doc["id"], stats)
            if r:
                checked.append(r)

        self._last_auditor = ""
        audits = self._audit(chunk, [q for q, _ in checked], lang)
        final: list[tuple[QuestionDraft, dict[str, Any], dict[str, Any]]] = []
        for i, (q, loc) in enumerate(checked):
            a = audits[i] if audits else None
            if a is None:
                final.append((q, loc, {"verdict": "unaudited"}))
                continue
            if a.verdict == "keep" and a.answer_supported and a.single_correct and a.in_scope:
                final.append((q, loc, a.model_dump()))
            elif a.verdict == "drop" or not a.answer_supported or not a.in_scope:
                self._reject(
                    doc["id"],
                    "audit",
                    "; ".join(a.issues) or "dropped by auditor",
                    {"q": q.model_dump(), "audit": a.model_dump()},
                    stats,
                )
            else:
                fixed = self._repair(doc, chunk, q, a, lang, stats)
                if fixed:
                    stats.repaired += 1
                    final.append(fixed)

        self._store(doc, row, final, generator, stats)
        return stats

    def _repair(
        self,
        doc: dict[str, Any],
        chunk: Chunk,
        q: QuestionDraft,
        a: AuditItem,
        lang: str,
        stats: ChunkStats,
    ) -> tuple[QuestionDraft, dict[str, Any], dict[str, Any]] | None:
        instructions = a.fix_instructions or "; ".join(a.issues)
        try:
            batch, _ = self.router.call(
                "generator",
                prompts.REPAIR_SYSTEM.format(lang=lang),
                prompts.repair_user(chunk.text, q.model_dump(), instructions),
                QuestionBatch,
                temperature=0.3,
            )
            if not batch.questions:
                raise LLMError("empty repair")
            checked = self._code_check(batch.questions[0], chunk, doc["id"], stats)
            if not checked:
                return None
            nq, loc = checked
            re_audit = self._audit(chunk, [nq], lang)
            ra = re_audit[0] if re_audit else None
            if (
                ra
                and ra.verdict == "keep"
                and ra.answer_supported
                and ra.single_correct
                and ra.in_scope
            ):
                d = ra.model_dump()
                d["repaired"] = True
                d["first_issues"] = a.issues
                return nq, loc, d
            self._reject(
                doc["id"],
                "repair",
                "still failing after repair: " + "; ".join(ra.issues if ra else []),
                nq.model_dump(),
                stats,
            )
        except LLMError as e:
            self._reject(doc["id"], "repair", f"repair failed: {e}", q.model_dump(), stats)
        return None

    def _store(
        self,
        doc: dict[str, Any],
        row: dict[str, Any],
        items: list[tuple[QuestionDraft, dict[str, Any], dict[str, Any]]],
        generator: str,
        stats: ChunkStats,
    ) -> None:
        if not items:
            return
        vecs = self.embedder.encode([f"{q.stem} {q.answer}" for q, _, _ in items])
        prev = self.db.all(
            "SELECT embedding FROM questions WHERE document_id=? AND status!='dropped' AND embedding IS NOT NULL",
            (doc["id"],),
        )
        pool = [
            v
            for v in (from_blob(p["embedding"]) for p in prev)
            if v is not None and v.shape[0] == vecs.shape[1]
        ]
        bank = np.stack(pool) if pool else np.zeros((0, vecs.shape[1]), dtype=np.float32)
        for (q, loc, audit), v in zip(items, vecs, strict=True):
            if bank.shape[0] and float((bank @ v).max()) >= self.s.dedup_threshold:
                self._reject(
                    doc["id"],
                    "duplicate",
                    "near-duplicate of an existing question",
                    q.model_dump(),
                    stats,
                )
                continue
            qid = self.db.insert(
                "questions",
                {
                    "document_id": doc["id"],
                    "topic_id": row["topic_id"],
                    "chunk_id": row["id"],
                    "type": q.type,
                    "difficulty": q.difficulty,
                    "stem": q.stem,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "answer": q.answer,
                    "accepted": q.accepted,
                    "key_points": q.key_points,
                    "explanation": q.explanation,
                    "source_quote": q.source_quote,
                    "source_loc": loc,
                    "audit": audit,
                    "generator": generator,
                    "auditor": self._last_auditor,
                    "embedding": to_blob(v),
                    "created_at": now(),
                },
            )
            from kavra.study.scheduler import ensure_card

            ensure_card(self.db, qid)
            bank = np.vstack([bank, v[None, :]])
            stats.kept += 1

    # -------------------------------------------------------------------- run
    def run(self, doc_id: int, progress: Progress | None = None) -> dict[str, Any]:
        progress = progress or (lambda p, s, m: None)
        doc = self.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
        if not doc:
            raise ValueError(f"document {doc_id} not found")
        chunks = self.db.all("SELECT * FROM chunks WHERE document_id=? ORDER BY idx", (doc_id,))
        progress(0.05, "topics", f"{len(chunks)} parça")
        self.build_topics(doc, chunks)
        topics = {
            t["id"]: t for t in self.db.all("SELECT * FROM topics WHERE document_id=?", (doc_id,))
        }
        chunks = self.db.all("SELECT * FROM chunks WHERE document_id=? ORDER BY idx", (doc_id,))
        todo = [c for c in chunks if not c["processed"]]
        totals = ChunkStats()
        failures: list[str] = []
        for i, row in enumerate(todo):
            progress(0.1 + 0.88 * i / max(1, len(todo)), "questions", f"{i + 1}/{len(todo)}")
            try:
                st = self.process_chunk(doc, row, topics.get(row["topic_id"]))
            except LLMError as e:
                log.warning("chunk %s failed: %s", row["id"], e)
                failures.append(str(e))
                continue
            self.db.execute("UPDATE chunks SET processed=1 WHERE id=?", (row["id"],))
            totals.generated += st.generated
            totals.kept += st.kept
            totals.repaired += st.repaired
            for k, v in st.rejected.items():
                totals.rejected[k] = totals.rejected.get(k, 0) + v
        remaining = self.db.scalar(
            "SELECT COUNT(*) FROM chunks WHERE document_id=? AND processed=0", (doc_id,)
        )
        summary = {
            "generated": totals.generated,
            "kept": totals.kept,
            "repaired": totals.repaired,
            "rejected": totals.rejected,
            "remaining_chunks": remaining,
            "errors": failures[-3:],
        }
        progress(
            1.0, "done" if not remaining else "partial", json.dumps(summary, ensure_ascii=False)
        )
        return summary


def _missing_audit(i: int) -> AuditItem:
    return AuditItem(
        index=i,
        answer_supported=False,
        single_correct=False,
        distractors_ok=False,
        in_scope=False,
        language_ok=False,
        distractor_quality=1,
        issues=["auditor returned no verdict"],
        verdict="drop",
        fix_instructions="",
    )
