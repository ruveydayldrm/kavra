"""Kavra evaluation harness (`make eval`).

Runs every document in eval/data through two configurations and scores the output:

  single   : generator only (code checks still apply)          -- ablation baseline
  pipeline : generate -> verify quote -> audit (2nd model) -> repair -> dedup

Metrics
  - candidates / kept / rejected by stage, auditor rejection rate
  - source accuracy   : kept questions whose quote is verbatim in the excerpt AND the judge
                        agrees the quote proves the answer
  - validity          : LLM-judge (a third model, not generator/auditor) says the question is
                        answerable from the excerpt with exactly one correct answer
  - answer clarity, distractor quality (1-5) from the same judge
  - open-answer grading agreement with human labels (eval/labels/open_grading.jsonl)
  - cost (always 0 on free tiers) and wall time
A CSV sample is written for manual review; fill the `human_valid` column and rerun with
`--manual <csv>` to report human-checked validity next to the judge's.

Usage (from backend/):  uv run python ../eval/run.py [--configs single,pipeline] [--docs tr_*]
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Literal

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
sys.path.insert(0, str(ROOT / "backend" / "src"))

from pydantic import BaseModel, Field  # noqa: E402

from kavra.config import Settings, get_settings  # noqa: E402
from kavra.db import Database, set_db  # noqa: E402
from kavra.llm.router import Router, build_provider, build_router  # noqa: E402
from kavra.pipeline.run import Pipeline  # noqa: E402
from kavra.pipeline.verify import locate_quote  # noqa: E402
from kavra.service import Service  # noqa: E402
from kavra.study.grading import grade_open  # noqa: E402


class JudgeItem(BaseModel):
    index: int
    valid: bool = Field(description="Answerable from the excerpt alone with exactly one correct answer")
    quote_supports: bool = Field(description="The quoted source sentence proves the stated answer")
    clear: bool = Field(description="Unambiguous, well-formed wording")
    distractor_quality: int = Field(description="1-5 for mcq; 3 for other types")
    note: str


class Judgement(BaseModel):
    items: list[JudgeItem]


JUDGE_SYSTEM = """You are an independent examiner checking study questions against the source excerpt.
Judge each question strictly and only against the excerpt. Return JSON only."""


def judge_chunk(router: Router, excerpt: str, qs: list[dict[str, Any]]) -> list[JudgeItem]:
    view = [
        {"index": i, "type": q["type"], "stem": q["stem"], "options": json.loads(q["options"]), "answer": q["answer"], "source_quote": q["source_quote"]}
        for i, q in enumerate(qs)
    ]
    user = 'EXCERPT:\n"""\n' + excerpt + '\n"""\n\nQUESTIONS:\n' + json.dumps(view, ensure_ascii=False, indent=1)
    res, _ = router.call("judge", JUDGE_SYSTEM, user, Judgement, temperature=0.0)
    by = {it.index: it for it in res.items}
    return [by.get(i) or JudgeItem(index=i, valid=False, quote_supports=False, clear=False, distractor_quality=1, note="missing") for i in range(len(qs))]


def run_config(name: Literal["single", "pipeline"], docs: list[Path], s: Settings, out: Path, judge: Router | None) -> dict[str, Any]:
    db = Database(out / f"{name}.db")
    set_db(db)
    s.single_model = name == "single"
    router = build_router(s, db)
    svc = Service(db, s, router)
    t0 = time.time()
    per_doc = []
    sample_rows: list[dict[str, Any]] = []
    for path in docs:
        res = svc.add_file(path.name, path, "text")
        svc.ingest_document(res["id"])
        d0 = time.time()
        summary = Pipeline(db, router, s).run(res["id"])
        qs = db.all("SELECT q.*, c.text AS excerpt FROM questions q JOIN chunks c ON c.id=q.chunk_id WHERE q.document_id=?", (res["id"],))
        verbatim = sum(1 for q in qs if locate_quote(q["excerpt"], q["source_quote"], 99) is not None)
        judged: list[tuple[dict[str, Any], JudgeItem]] = []
        if judge:
            by_chunk: dict[int, list[dict[str, Any]]] = {}
            for q in qs:
                by_chunk.setdefault(q["chunk_id"], []).append(q)
            for group in by_chunk.values():
                try:
                    judged += list(zip(group, judge_chunk(judge, group[0]["excerpt"], group), strict=True))
                except Exception as e:  # judge quota etc.: report what we have
                    print(f"  judge failed: {e}")
        for q, j in judged:
            sample_rows.append(
                {"config": name, "doc": path.stem, "id": q["id"], "type": q["type"], "stem": q["stem"], "options": q["options"], "answer": q["answer"],
                 "source_quote": q["source_quote"], "judge_valid": j.valid, "judge_note": j.note, "human_valid": ""}
            )
        mcq = [j for q, j in judged if q["type"] == "mcq"]
        per_doc.append(
            {
                "doc": path.stem,
                "lang": "tr" if path.stem.startswith("tr_") else "en",
                "candidates": summary["generated"],
                "kept": summary["kept"],
                "rejected": summary["rejected"],
                "repaired": summary["repaired"],
                "verbatim_quotes": verbatim,
                "judged": len(judged),
                "valid": sum(j.valid for _, j in judged),
                "quote_supports": sum(j.valid and j.quote_supports for _, j in judged),
                "clear": sum(j.clear for _, j in judged),
                "distractor_sum": sum(j.distractor_quality for j in mcq),
                "mcq": len(mcq),
                "seconds": round(time.time() - d0, 1),
            }
        )
        print(f"  [{name}] {path.stem}: kept {summary['kept']}/{summary['generated']}  rejected={summary['rejected']}")
    calls = db.one("SELECT COUNT(*) n, SUM(cached) c FROM llm_calls WHERE cached=0") or {}
    return {"config": name, "docs": per_doc, "seconds": round(time.time() - t0, 1), "llm_calls": calls.get("n", 0), "samples": sample_rows}


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    d = run["docs"]
    tot = lambda k: sum(x[k] for x in d)  # noqa: E731
    cand, kept, judged = tot("candidates"), tot("kept"), tot("judged")
    audit_rej = sum(x["rejected"].get("audit", 0) + x["rejected"].get("repair", 0) for x in d)
    code_rej = sum(x["rejected"].get("schema", 0) + x["rejected"].get("quote", 0) for x in d)
    return {
        "config": run["config"],
        "candidates": cand,
        "kept": kept,
        "code_rejected": code_rej,
        "audit_rejected": audit_rej,
        "auditor_reject_rate": round(audit_rej / max(1, cand - code_rej), 3),
        "valid_rate": round(tot("valid") / judged, 3) if judged else None,
        "source_accuracy": round(tot("quote_supports") / judged, 3) if judged else None,
        "verbatim_quote_rate": round(tot("verbatim_quotes") / kept, 3) if kept else None,
        "clarity": round(tot("clear") / judged, 3) if judged else None,
        "distractor_quality": round(tot("distractor_sum") / tot("mcq"), 2) if tot("mcq") else None,
        "llm_calls": run["llm_calls"],
        "cost_usd": 0.0,
        "seconds": run["seconds"],
    }


def grading_agreement() -> dict[str, Any]:
    rows = [json.loads(line) for line in (EVAL / "labels" / "open_grading.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    preds, gold = [], []
    for r in rows:
        preds.append(grade_open(r["key_points"], r["answer"])["score"])
        gold.append(r["human_score"])
    n = len(rows)
    mae = sum(abs(p - g) for p, g in zip(preds, gold, strict=True)) / n
    mp, mg = sum(preds) / n, sum(gold) / n
    cov = sum((p - mp) * (g - mg) for p, g in zip(preds, gold, strict=True))
    sp = sum((p - mp) ** 2 for p in preds) ** 0.5
    sg = sum((g - mg) ** 2 for g in gold) ** 0.5
    pass_agree = sum((p >= 0.6) == (g >= 0.6) for p, g in zip(preds, gold, strict=True)) / n
    return {"n": n, "mae": round(mae, 3), "pearson": round(cov / (sp * sg), 3) if sp and sg else None, "pass_fail_agreement": round(pass_agree, 3)}


def table(summaries: list[dict[str, Any]], grading: dict[str, Any], manual: dict[str, float] | None) -> str:
    def f(v: Any, pct: bool = True) -> str:
        if v is None:
            return "—"
        return f"{v * 100:.0f}%" if pct and isinstance(v, float) else str(v)

    names = {"single": "Single model", "pipeline": "Generate + audit"}
    lines = [
        "| Metric | " + " | ".join(names[s["config"]] for s in summaries) + " |",
        "|---|" + "---|" * len(summaries),
    ]
    rows = [
        ("Valid questions (LLM judge)", "valid_rate", True),
        ("Source accuracy (quote proves answer)", "source_accuracy", True),
        ("Verbatim source quote", "verbatim_quote_rate", True),
        ("Answer clarity", "clarity", True),
        ("Distractor quality (1-5)", "distractor_quality", False),
        ("Candidates → kept", None, False),
        ("Rejected by auditor", "auditor_reject_rate", True),
        ("LLM calls", "llm_calls", False),
        ("Cost", None, False),
        ("Wall time (s)", "seconds", False),
    ]
    for label, key, pct in rows:
        if label == "Candidates → kept":
            cells = [f"{s['candidates']} → {s['kept']}" for s in summaries]
        elif label == "Cost":
            cells = ["$0" for _ in summaries]
        else:
            cells = [f(s[key], pct) for s in summaries]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if manual:
        lines.append("| Valid questions (human-checked sample) | " + " | ".join(f(manual.get(s["config"])) for s in summaries) + " |")
    lines += [
        "",
        f"Open-answer grading vs. human labels (n={grading['n']}): MAE {grading['mae']}, Pearson r {grading['pearson']}, pass/fail agreement {f(grading['pass_fail_agreement'])}.",
    ]
    return "\n".join(lines)


def manual_scores(path: Path) -> dict[str, float]:
    by: dict[str, list[int]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            v = row.get("human_valid", "").strip().lower()
            if v in ("1", "0", "true", "false", "y", "n"):
                by.setdefault(row["config"], []).append(int(v in ("1", "true", "y")))
    return {k: sum(v) / len(v) for k, v in by.items() if v}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="single,pipeline")
    ap.add_argument("--docs", default="*")
    ap.add_argument("--judge", default=os.environ.get("JUDGE", "groq:qwen/qwen3.8-27b"))
    ap.add_argument("--manual", type=Path)
    ap.add_argument("--grading-only", action="store_true")
    ap.add_argument("--update-readme", action="store_true")
    args = ap.parse_args()

    grading = grading_agreement()
    print("open grading agreement:", grading)
    if args.grading_only:
        return

    s = get_settings()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = EVAL / "runs" / stamp
    out.mkdir(parents=True, exist_ok=True)
    s.data_dir = out
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    docs = sorted(p for p in (EVAL / "data").glob("*.md") if fnmatch.fnmatch(p.stem, args.docs))

    judge_db = Database(out / "judge.db")
    jp = build_provider(args.judge, s)
    judge = Router({"judge": [jp]}, db=judge_db) if jp else None
    if judge is None:
        print("! no judge provider; validity metrics will be empty")

    runs = [run_config(c.strip(), docs, s, out, judge) for c in args.configs.split(",")]  # type: ignore[arg-type]
    summaries = [summarize(r) for r in runs]

    samples = [row for r in runs for row in r["samples"]]
    random.Random(7).shuffle(samples)
    with (out / "manual_review.csv").open("w", newline="", encoding="utf-8") as fh:
        if samples:
            w = csv.DictWriter(fh, fieldnames=list(samples[0]))
            w.writeheader()
            w.writerows(samples[:60])

    manual = manual_scores(args.manual) if args.manual else None
    md = table(summaries, grading, manual)
    meta = {"stamp": stamp, "judge": args.judge, "generator": s.generator, "auditor": s.auditor, "local_mode": s.local_mode, "docs": [d.stem for d in docs]}
    (out / "results.json").write_text(json.dumps({"meta": meta, "summary": summaries, "grading": grading, "runs": [{k: v for k, v in r.items() if k != "samples"} for r in runs]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVAL / "results").mkdir(exist_ok=True)
    (EVAL / "results" / "latest.md").write_text(f"<!-- {json.dumps(meta, ensure_ascii=False)} -->\n\n{md}\n", encoding="utf-8")
    print("\n" + md)
    if args.update_readme:
        readme = ROOT / "README.md"
        txt = readme.read_text(encoding="utf-8")
        start, end = "<!-- EVAL:START -->", "<!-- EVAL:END -->"
        if start in txt and end in txt:
            head, rest = txt.split(start, 1)
            _, tail = rest.split(end, 1)
            note = f"\n_Run {stamp} · generator `{s.generator}` · auditor `{s.auditor}` · judge `{args.judge}` · {len(docs)} documents (TR+EN)._\n\n"
            readme.write_text(head + start + note + md + "\n" + end + tail, encoding="utf-8")
            print("README updated")


if __name__ == "__main__":
    main()
