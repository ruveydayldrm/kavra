"""Deterministic checks that never trust the model.

The most important one: `locate_quote` — the claimed source sentence must actually exist in
the excerpt (fuzzy, to survive whitespace/quote-style differences). No match = no question.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from kavra.pipeline.schemas import QuestionDraft

_TRANS = str.maketrans(
    {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", " ": " "}
)


def _norm_char(ch: str) -> str:
    ch = ch.translate(_TRANS)
    if ch in "İI":
        return "i"
    low = ch.lower()
    return low if len(low) == 1 else unicodedata.normalize("NFC", low)[:1]


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase + unify punctuation + collapse whitespace, keeping a map to original offsets."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
            continue
        out.append(_norm_char(ch))
        idx.append(i)
        prev_space = False
    return "".join(out), idx


def normalize(text: str) -> str:
    return normalize_with_map(text)[0].strip()


@dataclass
class QuoteMatch:
    start: int
    end: int
    score: float


def locate_quote(excerpt: str, quote: str, threshold: float = 88.0) -> QuoteMatch | None:
    q = normalize(quote).strip(" .\"'")
    if len(q) < 12:
        return None
    t, idx = normalize_with_map(excerpt)
    pos = t.find(q)
    if pos >= 0:
        return QuoteMatch(idx[pos], idx[pos + len(q) - 1] + 1, 100.0)
    al = fuzz.partial_ratio_alignment(q, t, score_cutoff=threshold)
    if al is None or al.dest_end <= al.dest_start:
        return None
    # require the aligned span to be roughly as long as the quote (no "short quote" cheating)
    if (al.dest_end - al.dest_start) < 0.8 * len(q):
        return None
    return QuoteMatch(idx[al.dest_start], idx[al.dest_end - 1] + 1, float(al.score))


BLANK = re.compile(r"_{2,}|\.{4,}|\[\s*\]|\(\s*\)")
TRUE_WORDS = {"true", "doğru", "dogru", "evet", "t", "d"}
FALSE_WORDS = {"false", "yanlış", "yanlis", "hayır", "f", "y"}


def structural_issues(q: QuestionDraft, excerpt: str) -> tuple[QuestionDraft, list[str]]:
    """Validate shape; silently repair trivial inconsistencies. Returns (question, issues)."""
    issues: list[str] = []
    q = q.model_copy(deep=True)
    if len(q.stem) < 8:
        issues.append("stem too short")
    if q.type == "mcq":
        opts = [o.strip() for o in q.options]
        if len(opts) != 4:
            issues.append(f"mcq needs 4 options, got {len(opts)}")
        elif len({normalize(o) for o in opts}) != 4:
            issues.append("duplicate options")
        if not 0 <= q.correct_index < len(opts):
            match = [i for i, o in enumerate(opts) if normalize(o) == normalize(q.answer)]
            if match:
                q.correct_index = match[0]
            else:
                issues.append("correct_index out of range")
        elif normalize(opts[q.correct_index]) != normalize(q.answer):
            match = [i for i, o in enumerate(opts) if normalize(o) == normalize(q.answer)]
            if len(match) == 1:
                q.correct_index = match[0]
            else:
                q.answer = opts[q.correct_index]
        q.options = opts
        if (
            not issues
            and normalize(q.options[q.correct_index]) in normalize(q.stem)
            and len(q.answer) > 6
        ):
            issues.append("answer leaked in stem")
    elif q.type == "tf":
        a = normalize(q.answer)
        if a in TRUE_WORDS:
            q.answer = "true"
        elif a in FALSE_WORDS:
            q.answer = "false"
        else:
            issues.append("tf answer must be true/false")
        q.options, q.correct_index = [], -1
    elif q.type == "cloze":
        if not BLANK.search(q.stem):
            issues.append("cloze stem has no blank")
        else:
            q.stem = BLANK.sub("____", q.stem, count=1)
            if len(BLANK.findall(q.stem)) > 1:
                issues.append("cloze has more than one blank")
        if fuzz.partial_ratio(normalize(q.answer), normalize(excerpt)) < 85:
            issues.append("cloze answer not in excerpt")
        q.options, q.correct_index = [], -1
    elif q.type == "open":
        q.key_points = [k.strip() for k in q.key_points if k.strip()]
        if not 2 <= len(q.key_points) <= 6:
            issues.append("open question needs 2-6 key points")
        q.options, q.correct_index = [], -1
    return q, issues
