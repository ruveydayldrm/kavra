from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ["EMBEDDER"] = "hash"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["LOCAL_MODE"] = "false"

from kavra.config import get_settings  # noqa: E402
from kavra.db import Database, set_db  # noqa: E402
from kavra.embed import HashEmbedder, set_embedder  # noqa: E402
from kavra.llm import FakeProvider, Router  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

NOTES = """Fotosentez, bitkilerin ışık enerjisini kimyasal enerjiye dönüştürdüğü süreçtir.
Fotosentez kloroplastlarda gerçekleşir ve klorofil pigmenti ışığı soğurur.
Işığa bağımlı tepkimeler tilakoit zarında gerçekleşir ve ATP ile NADPH üretir.
Calvin döngüsü stromada gerçekleşir ve karbondioksiti glikoza dönüştürür.

Hücresel solunum mitokondride gerçekleşir ve glikozdan ATP üretir.
Oksijenli solunumda son elektron alıcısı oksijendir.
Glikoliz sitoplazmada gerçekleşir ve oksijen gerektirmez.
Krebs döngüsü mitokondri matriksinde gerçekleşir."""


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text) if len(s.strip()) > 20]


def fake_generator(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    if "topic map" in system:
        ids = [int(x) for x in re.findall(r"^\[(\d+)\]", user, re.M)]
        half = max(1, len(ids) // 2)
        return {
            "topics": [
                {
                    "title": "Fotosentez",
                    "summary": "Işık ve Calvin",
                    "chunk_ids": ids[:half],
                    "misconceptions": ["Fotosentez mitokondride olur"],
                },
                {
                    "title": "Solunum",
                    "summary": "ATP üretimi",
                    "chunk_ids": ids[half:],
                    "misconceptions": ["Glikoliz oksijen ister"],
                },
            ]
        }
    excerpt = user.split('"""')[1].strip()
    sents = sentences(excerpt)
    if "fixes a single" in system:
        s = sents[0]
        return {"questions": [_mcq(s, "Onarılmış: " + s[:40] + "?")]}
    qs = []
    for i, s in enumerate(sents[:3]):
        qs.append(_mcq(s, f"Soru {i}: '{s.split()[-2]}' ifadesiyle ilgili hangisi doğrudur?"))
    qs.append(
        {
            **_mcq(sents[0], "Uydurma kaynaklı soru?"),
            "source_quote": "Bu cümle notlarda hiç geçmiyor ve uydurmadır.",
        }
    )
    return {"questions": qs}


def _mcq(sentence: str, stem: str) -> dict[str, Any]:
    return {
        "type": "mcq",
        "difficulty": "medium",
        "stem": stem,
        "options": [sentence[:30], "Yanlış seçenek A", "Yanlış seçenek B", "Yanlış seçenek C"],
        "correct_index": 0,
        "answer": sentence[:30],
        "accepted": [],
        "key_points": [],
        "explanation": "Notta açıkça yazıyor.",
        "source_quote": sentence,
    }


def fake_auditor(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    import json

    qs = json.loads(user.split("QUESTIONS:\n", 1)[1])
    items = []
    for q in qs:
        verdict = "keep"
        if q["stem"].startswith("Soru 1"):
            verdict = "fix"
        if q["stem"].startswith("Soru 2"):
            verdict = "drop"
        items.append(
            {
                "index": q["index"],
                "answer_supported": verdict != "drop",
                "single_correct": True,
                "distractors_ok": True,
                "in_scope": True,
                "language_ok": True,
                "distractor_quality": 3,
                "issues": [] if verdict == "keep" else ["x"],
                "verdict": verdict,
                "fix_instructions": "çeldiricileri iyileştir" if verdict == "fix" else "",
            }
        )
    return {"items": items}


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "t.db")
    set_db(d)
    set_embedder(HashEmbedder())
    s = get_settings()
    s.data_dir = tmp_path
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    yield d
    set_db(None)


@pytest.fixture()
def router(db: Database) -> Router:
    gen = FakeProvider(fake_generator, name="fakegen", model="g1")
    aud = FakeProvider(fake_auditor, name="fakeaud", model="a1")
    return Router({"generator": [gen], "auditor": [aud]}, db=db)
