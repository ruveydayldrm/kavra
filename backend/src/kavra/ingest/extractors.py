"""Format-specific extractors. Each returns `Segment`s with precise locators."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from kavra.ingest import Segment

log = logging.getLogger("kavra.ingest")


def pdf(path: Path) -> list[Segment]:
    """One segment per text block; line numbers count text lines on the page (1-based)."""
    import pymupdf

    out: list[Segment] = []
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            line_no = 0
            blocks = page.get_text("dict", sort=True)["blocks"]
            for b in blocks:
                if b.get("type") != 0:
                    continue
                lines = []
                for ln in b.get("lines", []):
                    t = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
                    if t:
                        lines.append(t)
                if not lines:
                    continue
                first = line_no + 1
                line_no += len(lines)
                text = " ".join(lines)
                # Re-join words hyphenated across lines ("öğren- me" -> "öğrenme")
                text = text.replace("- ", "") if text.count("- ") > 2 else text
                out.append(
                    Segment(
                        text,
                        {"kind": "page", "page": pno, "line_start": first, "line_end": line_no},
                    )
                )
    if not out:
        log.info("PDF has no text layer; falling back to OCR")
        return pdf_ocr(path)
    return out


def pdf_ocr(path: Path) -> list[Segment]:
    import pymupdf

    out: list[Segment] = []
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            png = page.get_pixmap(dpi=200).tobytes("png")
            for i, line in enumerate(_ocr_lines(png), start=1):
                out.append(
                    Segment(line, {"kind": "page", "page": pno, "line_start": i, "line_end": i})
                )
    return out


def pptx(path: Path) -> list[Segment]:
    from pptx import Presentation

    out: list[Segment] = []
    prs = Presentation(str(path))
    for sno, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(r.text for r in para.runs).strip()
                    if t:
                        texts.append(t)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        texts.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                texts.append(notes)
        if texts:
            out.append(
                Segment(
                    ". ".join(t.rstrip(".") for t in texts) + ".", {"kind": "slide", "slide": sno}
                )
            )
    return out


def docx(path: Path) -> list[Segment]:
    import docx as pydocx

    d = pydocx.Document(str(path))
    out: list[Segment] = []
    n = 0
    for para in d.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        n += 1
        out.append(Segment(t, {"kind": "para", "para": n}))
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                n += 1
                out.append(Segment(" | ".join(cells), {"kind": "para", "para": n}))
    return out


def text(path: Path) -> list[Segment]:
    out: list[Segment] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    para: list[str] = []
    start = 1
    for i, line in enumerate(raw.splitlines() + [""], start=1):
        if line.strip():
            if not para:
                start = i
            para.append(line.strip())
        elif para:
            out.append(
                Segment(
                    " ".join(para),
                    {"kind": "page", "page": 1, "line_start": start, "line_end": i - 1},
                )
            )
            para = []
    return out


def image(path: Path) -> list[Segment]:
    lines = _ocr_lines(path.read_bytes())
    # group every 3 OCR lines so segments carry enough context
    out: list[Segment] = []
    for i in range(0, len(lines), 3):
        group = lines[i : i + 3]
        out.append(
            Segment(
                " ".join(group), {"kind": "image", "line_start": i + 1, "line_end": i + len(group)}
            )
        )
    return out


@lru_cache(maxsize=1)
def _ocr_engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _ocr_lines(data: bytes) -> list[str]:
    result, _ = _ocr_engine()(data)
    if not result:
        return []
    # result: [[box, text, score], ...]; sort top-to-bottom, then left-to-right
    rows = sorted(result, key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
    merged: list[str] = []
    last_y: float | None = None
    for box, txt, score in rows:
        if float(score) < 0.5:
            continue
        y = box[0][1]
        if last_y is not None and abs(y - last_y) < 12 and merged:
            merged[-1] += " " + txt
        else:
            merged.append(txt)
        last_y = y
    return merged
