from pathlib import Path

import docx
import pymupdf
from pptx import Presentation

from kavra.ingest import Segment, build_chunks, detect_lang, extractors
from kavra.ingest.youtube import choose_transcript, video_id


def test_chunks_keep_locators_and_resolve_quotes():
    segs = [
        Segment(
            f"Cümle numarası {i} burada yer alır ve yeterince uzundur.",
            {"kind": "page", "page": 1 + i // 3, "line_start": i, "line_end": i},
        )
        for i in range(12)
    ]
    chunks = build_chunks(segs, target=200)
    assert len(chunks) > 1
    c = chunks[1]
    start = c.text.index("Cümle")
    loc = c.locate(start, start + 10)
    assert loc["kind"] == "page" and loc["line_start"] == loc["line_end"]


def test_pdf_extract_page_and_lines(tmp_path: Path):
    p = tmp_path / "n.pdf"
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), f"Sayfa {i + 1} başlığı", fontsize=14)
        page.insert_text((72, 120), "Mitoz bölünmede iki özdeş hücre oluşur.", fontsize=11)
    doc.save(p)
    segs = extractors.pdf(p)
    assert {s.loc["page"] for s in segs} == {1, 2}
    assert all(s.loc["line_start"] >= 1 for s in segs)
    assert any("Mitoz" in s.text for s in segs)


def test_docx_and_pptx(tmp_path: Path):
    d = docx.Document()
    d.add_paragraph("Birinci paragraf metni.")
    d.add_paragraph("")
    d.add_paragraph("İkinci paragraf metni.")
    d.save(tmp_path / "a.docx")
    segs = extractors.docx(tmp_path / "a.docx")
    assert [s.loc["para"] for s in segs] == [1, 2]

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Hücre zarı"
    s.placeholders[1].text = "Seçici geçirgendir"
    prs.save(tmp_path / "b.pptx")
    segs = extractors.pptx(tmp_path / "b.pptx")
    assert segs[0].loc == {"kind": "slide", "slide": 1}
    assert "Seçici" in segs[0].text


def test_detect_lang():
    assert detect_lang("Bu bir deneme metnidir ve hücre zarı için önemlidir.") == "tr"
    assert detect_lang("This is the membrane of the cell and it is selective.") == "en"


def test_video_id():
    assert video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10") == "dQw4w9WgXcQ"
    assert video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("nope") is None


class T:
    def __init__(self, code: str, generated: bool):
        self.language_code, self.is_generated = code, generated


def test_choose_original_track_on_dubbed_video():
    listing = [T("en", True), T("tr", True), T("es", True)]
    assert choose_transcript(listing, "Hücre biyolojisi dersi", original="tr").language_code == "tr"
    # no metadata: title language decides between generated tracks
    assert (
        choose_transcript(
            listing, "Hücre biyolojisi ve zar yapısı için ders", original=None
        ).language_code
        == "tr"
    )
    # manual track wins over generated ones when original unknown
    assert choose_transcript([T("en", True), T("de", False)], "x", None).language_code == "de"
