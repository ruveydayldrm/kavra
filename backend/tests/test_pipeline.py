import json
from pathlib import Path

from conftest import NOTES

from kavra.db import Database
from kavra.llm import FakeProvider, Router
from kavra.pipeline.run import Pipeline
from kavra.service import Service


def _ingest(db: Database, router: Router, tmp_path: Path) -> int:
    f = tmp_path / "notlar.txt"
    f.write_text(NOTES, encoding="utf-8")
    svc = Service(db, router=router)
    svc.s.chunk_chars = 260
    res = svc.add_file("notlar.txt", f, "text")
    svc.ingest_document(res["id"])
    return res["id"]


def test_full_pipeline_rules(db: Database, router: Router, tmp_path: Path):
    doc_id = _ingest(db, router, tmp_path)
    summary = Pipeline(db, router).run(doc_id)
    assert summary["remaining_chunks"] == 0
    rejected = summary["rejected"]
    # every chunk had one fabricated quote -> rejected by code, before the auditor
    assert rejected.get("quote", 0) >= 2
    # auditor dropped "Soru 2" questions
    assert rejected.get("audit", 0) >= 1
    assert summary["repaired"] >= 1
    qs = db.all("SELECT * FROM questions WHERE document_id=?", (doc_id,))
    assert qs
    for q in qs:
        loc = json.loads(q["source_loc"])
        assert loc["kind"] == "page" and loc["line_start"] >= 1
        assert (
            q["source_quote"]
            in db.one("SELECT text FROM chunks WHERE id=?", (q["chunk_id"],))["text"]
        )
        assert q["generator"] == "fakegen:g1" and q["auditor"] == "fakeaud:a1"
    # topics were built and every question has a card
    assert db.scalar("SELECT COUNT(*) FROM topics WHERE document_id=?", (doc_id,)) == 2
    assert db.scalar("SELECT COUNT(*) FROM cards") == len(qs)


def test_pipeline_is_idempotent_and_cached(db: Database, router: Router, tmp_path: Path):
    doc_id = _ingest(db, router, tmp_path)
    Pipeline(db, router).run(doc_id)
    n = db.scalar("SELECT COUNT(*) FROM questions")
    calls = len(router.chains["generator"][0].calls)  # type: ignore[attr-defined]
    Pipeline(db, router).run(doc_id)  # finished chunks are skipped
    assert len(router.chains["generator"][0].calls) == calls  # type: ignore[attr-defined]
    db.execute("UPDATE chunks SET processed=0")
    Pipeline(db, router).run(doc_id)  # forced re-run: near-duplicates are rejected
    assert db.scalar("SELECT COUNT(*) FROM questions") == n
    assert db.scalar("SELECT COUNT(*) FROM rejected WHERE stage='duplicate'") >= n


def test_auditor_never_same_model_as_generator(db: Database, tmp_path: Path):
    from conftest import fake_auditor, fake_generator

    shared = FakeProvider(
        lambda s, u, sc: (
            fake_auditor(s, u, sc) if "quality reviewer" in s else fake_generator(s, u, sc)
        ),
        name="same",
        model="m",
    )
    other = FakeProvider(fake_auditor, name="other", model="m2")
    r = Router({"generator": [shared], "auditor": [shared, other]}, db=db)
    doc_id = _ingest(db, r, tmp_path)
    Pipeline(db, r).run(doc_id)
    auditors = {q["auditor"] for q in db.all("SELECT auditor FROM questions")}
    assert auditors == {"other:m2"}


def test_single_model_ablation_skips_audit(db: Database, router: Router, tmp_path: Path):
    doc_id = _ingest(db, router, tmp_path)
    p = Pipeline(db, router)
    p.s.single_model = True
    try:
        p.run(doc_id)
    finally:
        p.s.single_model = False
    audits = {json.loads(q["audit"])["verdict"] for q in db.all("SELECT audit FROM questions")}
    assert audits == {"unaudited"}
    assert len(router.chains["auditor"][0].calls) == 0  # type: ignore[attr-defined]
