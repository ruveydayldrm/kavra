"""Document ingestion: every extractor yields `Segment`s that carry an exact locator.

A locator says where a piece of text lives in the original material:
  {"kind": "page",  "page": 3, "line_start": 12, "line_end": 18}
  {"kind": "slide", "slide": 7}
  {"kind": "para",  "para": 42}
  {"kind": "image", "line_start": 1, "line_end": 4}
  {"kind": "time",  "start": 93.2, "end": 101.0}
Chunks keep the char-offset -> locator map, so any quote found inside a chunk resolves back
to its page/line or video second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Segment:
    text: str
    loc: dict[str, Any]


@dataclass
class Chunk:
    idx: int
    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)  # {start, end, loc}

    def locate(self, start: int, end: int) -> dict[str, Any]:
        """Merge locators of every segment overlapping [start, end)."""
        hits = [s for s in self.segments if s["start"] < end and s["end"] > start]
        if not hits:
            hits = self.segments[:1]
        return merge_locs([h["loc"] for h in hits])


def merge_locs(locs: list[dict[str, Any]]) -> dict[str, Any]:
    if not locs:
        return {}
    first, last = locs[0], locs[-1]
    kind = first.get("kind")
    if kind == "page":
        if first["page"] == last["page"]:
            return {
                "kind": "page",
                "page": first["page"],
                "line_start": first["line_start"],
                "line_end": last["line_end"],
            }
        return {
            "kind": "page",
            "page": first["page"],
            "line_start": first["line_start"],
            "page_end": last["page"],
            "line_end": last["line_end"],
        }
    if kind == "time":
        return {"kind": "time", "start": first["start"], "end": last["end"]}
    if kind == "slide":
        return (
            {"kind": "slide", "slide": first["slide"], "slide_end": last["slide"]}
            if first["slide"] != last["slide"]
            else dict(first)
        )
    if kind == "para":
        return (
            {"kind": "para", "para": first["para"], "para_end": last["para"]}
            if first["para"] != last["para"]
            else dict(first)
        )
    if kind == "image":
        return {"kind": "image", "line_start": first["line_start"], "line_end": last["line_end"]}
    return dict(first)


WS = re.compile(r"[ \t ]+")


def clean(text: str) -> str:
    text = text.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return WS.sub(" ", text).strip()


def build_chunks(segments: list[Segment], target: int = 1600) -> list[Chunk]:
    """Greedy packing of segments into ~target-char chunks, never splitting a segment."""
    chunks: list[Chunk] = []
    buf: list[str] = []
    segs: list[dict[str, Any]] = []
    size = 0

    def flush() -> None:
        nonlocal buf, segs, size
        if buf and size >= 40:
            chunks.append(Chunk(idx=len(chunks), text="".join(buf).strip(), segments=segs))
        elif buf and chunks:  # tiny tail -> merge into previous chunk
            prev = chunks[-1]
            offset = len(prev.text) + 1
            prev.text = prev.text + "\n" + "".join(buf).strip()
            prev.segments.extend(
                {**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in segs
            )
        buf, segs, size = [], [], 0

    for seg in segments:
        t = clean(seg.text)
        if not t:
            continue
        if size and size + len(t) > target:
            flush()
        start = size
        buf.append(t + "\n")
        size += len(t) + 1
        segs.append({"start": start, "end": start + len(t), "loc": seg.loc})
    flush()
    return chunks


SUPPORTED = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".docx": "docx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".txt": "text",
    ".md": "text",
}


def kind_for(path: Path) -> str | None:
    return SUPPORTED.get(path.suffix.lower())


def extract(path: Path, kind: str) -> list[Segment]:
    from kavra.ingest import extractors

    fn = {
        "pdf": extractors.pdf,
        "pptx": extractors.pptx,
        "docx": extractors.docx,
        "image": extractors.image,
        "text": extractors.text,
    }[kind]
    return fn(path)


TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
TR_WORDS = {
    "ve",
    "bir",
    "bu",
    "ile",
    "için",
    "olarak",
    "da",
    "de",
    "olan",
    "gibi",
    "daha",
    "ise",
    "çok",
    "en",
    "veya",
    "ki",
    "değil",
}
EN_WORDS = {
    "the",
    "and",
    "of",
    "to",
    "is",
    "in",
    "that",
    "for",
    "are",
    "with",
    "as",
    "this",
    "be",
    "by",
    "or",
    "which",
}


def detect_lang(text: str) -> str:
    sample = text[:20000].lower()
    words = re.findall(r"[a-zçğıöşü]+", sample)
    tr = sum(w in TR_WORDS for w in words) + 3 * sum(ch in TR_CHARS for ch in sample) / 10
    en = sum(w in EN_WORDS for w in words)
    return "tr" if tr >= en else "en"
