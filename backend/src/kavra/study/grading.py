"""Answer checking. Runs locally and instantly (no LLM)."""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from kavra.embed import get_embedder
from kavra.pipeline.verify import normalize

STOP = {
    "ve",
    "bir",
    "bu",
    "ile",
    "için",
    "da",
    "de",
    "olan",
    "gibi",
    "the",
    "a",
    "an",
    "of",
    "and",
    "to",
    "is",
    "are",
    "in",
    "on",
    "that",
    "it",
    "olarak",
    "en",
    "çok",
    "daha",
    "ise",
    "veya",
    "or",
}


def _words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-zçğıöşü0-9]+", normalize(text)) if len(w) > 2 and w not in STOP
    }


def _stem_overlap(point: str, answer: str) -> float:
    """Share of key-point content words present in the answer, matching on 5-char prefixes
    so Turkish suffixes (mitokondri / mitokondride) still count."""
    pw = _words(point)
    if not pw:
        return 0.0
    aw = {w[:5] for w in _words(answer)}
    return sum(w[:5] in aw for w in pw) / len(pw)


def grade_open(key_points: list[str], response: str) -> dict[str, Any]:
    response = response.strip()
    if not key_points:
        return {"score": 0.0, "covered": [], "missing": []}
    if len(response) < 3:
        return {"score": 0.0, "covered": [], "missing": list(range(len(key_points)))}
    emb = get_embedder()
    sents = [s for s in re.split(r"(?<=[.!?;])\s+|\n", response) if len(s.strip()) > 2] or [
        response
    ]
    sents.append(response)
    kv = emb.encode(key_points)
    sv = emb.encode(sents)
    sims = (kv @ sv.T).max(axis=1) if sv.size else np.zeros(len(key_points))
    threshold = 0.62 if emb.name == "minilm" else 0.45
    covered, missing = [], []
    for i, kp in enumerate(key_points):
        ov = _stem_overlap(kp, response)
        if (
            float(sims[i]) >= threshold
            or ov >= 0.6
            or (float(sims[i]) >= threshold - 0.1 and ov >= 0.4)
        ):
            covered.append(i)
        else:
            missing.append(i)
    return {
        "score": round(len(covered) / len(key_points), 3),
        "covered": covered,
        "missing": missing,
    }


def check(q: dict[str, Any], response: Any) -> dict[str, Any]:
    """Return {correct, score, ...}. `q` is a questions row."""
    t = q["type"]
    if t == "mcq":
        try:
            idx = int(response)
        except (TypeError, ValueError):
            idx = -1
        ok = idx == q["correct_index"]
        return {"correct": ok, "score": 1.0 if ok else 0.0, "correct_index": q["correct_index"]}
    if t == "tf":
        val = str(response).lower() in ("true", "1", "doğru", "dogru")
        ok = ("true" if val else "false") == q["answer"]
        return {"correct": ok, "score": 1.0 if ok else 0.0, "answer": q["answer"]}
    if t == "cloze":
        given = normalize(str(response or "")).strip(" .")
        accepted = [q["answer"], *json.loads(q["accepted"] or "[]")]
        best = 0.0
        for a in accepted:
            na = normalize(a).strip(" .")
            if not na or not given:
                continue
            if given == na or (given.startswith(na) and len(given) - len(na) <= 5):
                best = 100.0
                break
            best = max(best, fuzz.ratio(given, na))
        ok = best >= 85
        return {
            "correct": ok,
            "score": 1.0 if ok else 0.0,
            "answer": q["answer"],
            "near_miss": 70 <= best < 85,
        }
    if t == "open":
        kps = json.loads(q["key_points"] or "[]")
        g = grade_open(kps, str(response or ""))
        g["correct"] = g["score"] >= 0.6
        g["key_points"] = kps
        return g
    raise ValueError(f"unknown question type {t}")


def auto_rating(result: dict[str, Any], duration_ms: int | None, qtype: str) -> int:
    """Map an outcome to an FSRS rating. Users may override (Hard/Easy) in the UI."""
    if not result["correct"]:
        return 1
    if qtype == "open" and result.get("score", 1) < 0.85:
        return 2
    if duration_ms is not None and duration_ms < 4000 and qtype in ("tf", "mcq"):
        return 3
    return 3
