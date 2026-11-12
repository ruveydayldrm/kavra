"""`kavra demo` — load the eval course notes with hand-written questions and a simulated
study history, so the app can be explored (and screenshotted) without any API key.

The questions are hand-written, but they still go through the *real* pipeline: schema checks,
verbatim source verification, dedup and FSRS card creation. Only the LLM is replaced by a
scripted provider. The review history is simulated and clearly marked as demo data.
"""

from __future__ import annotations

import json
import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fsrs import Rating

from kavra.config import get_settings
from kavra.db import Database, now
from kavra.llm import FakeProvider, Router
from kavra.pipeline.run import Pipeline
from kavra.pipeline.verify import normalize
from kavra.service import Service
from kavra.study import exam
from kavra.study.scheduler import load_card, scheduler

EVAL_DATA = Path(__file__).resolve().parents[3] / "eval" / "data"


def mcq(
    stem: str, options: list[str], quote: str, expl: str, diff: str = "medium", ci: int = 0
) -> dict[str, Any]:
    return {
        "type": "mcq",
        "difficulty": diff,
        "stem": stem,
        "options": options,
        "correct_index": ci,
        "answer": options[ci],
        "accepted": [],
        "key_points": [],
        "explanation": expl,
        "source_quote": quote,
    }


def tf(stem: str, value: bool, quote: str, expl: str, diff: str = "easy") -> dict[str, Any]:
    return {
        "type": "tf",
        "difficulty": diff,
        "stem": stem,
        "options": [],
        "correct_index": -1,
        "answer": "true" if value else "false",
        "accepted": [],
        "key_points": [],
        "explanation": expl,
        "source_quote": quote,
    }


def cloze(
    stem: str,
    answer: str,
    quote: str,
    expl: str,
    accepted: list[str] | None = None,
    diff: str = "easy",
) -> dict[str, Any]:
    return {
        "type": "cloze",
        "difficulty": diff,
        "stem": stem,
        "options": [],
        "correct_index": -1,
        "answer": answer,
        "accepted": accepted or [],
        "key_points": [],
        "explanation": expl,
        "source_quote": quote,
    }


def open_q(
    stem: str, model: str, kps: list[str], quote: str, expl: str, diff: str = "hard"
) -> dict[str, Any]:
    return {
        "type": "open",
        "difficulty": diff,
        "stem": stem,
        "options": [],
        "correct_index": -1,
        "answer": model,
        "accepted": [],
        "key_points": kps,
        "explanation": expl,
        "source_quote": quote,
    }


DEMO: dict[str, dict[str, Any]] = {
    "tr_hucre_biyolojisi": {
        "title": "Hücre Biyolojisi — Ünite 2",
        "questions": [
            mcq(
                "Aşağıdakilerden hangisi hem prokaryot hem de ökaryot hücrelerde bulunur?",
                ["Ribozom", "Mitokondri", "Golgi cisimciği", "Lizozom"],
                "Ribozom ise hem prokaryot hem de ökaryot hücrelerde bulunan zarsız bir organeldir.",
                "Ribozom zarsız bir organeldir; zarlı organeller (mitokondri, Golgi, lizozom) yalnızca ökaryotlarda bulunur.",
                "easy",
            ),
            tf(
                "Prokaryot hücrelerde kalıtım materyali çift katlı zarla çevrili bir çekirdeğin içindedir.",
                False,
                "Prokaryot hücrelerde çekirdek zarı yoktur ve kalıtım materyali sitoplazmada serbest hâlde bulunur.",
                "Çekirdek zarı ökaryotlara özgüdür; prokaryotlarda DNA sitoplazmada serbesttir.",
            ),
            cloze(
                "Günümüzde kabul gören hücre zarı modeli ____ modeldir.",
                "akıcı mozaik",
                "Günümüzde kabul gören zar modeli akıcı mozaik modeldir.",
                "Akıcı mozaik modele göre zar, fosfolipit çift tabakası ve içine gömülü proteinlerden oluşur.",
                ["akışkan mozaik"],
            ),
            mcq(
                "Hayvan hücrelerinin zarında bulunan ve zarın akışkanlığını düzenleyen molekül hangisidir?",
                ["Kolesterol", "Glikoprotein", "Selüloz", "Kitin"],
                "Kolesterol, hayvan hücrelerinin zarında bulunur ve zarın akışkanlığını düzenler.",
                "Glikoproteinler hücre tanımada görev alır; selüloz ve kitin zar molekülü değildir.",
            ),
            mcq(
                "Sodyum-potasyum pompası her ATP kullanımında ne yapar?",
                [
                    "3 Na⁺ dışarı çıkarır, 2 K⁺ içeri alır",
                    "2 Na⁺ dışarı çıkarır, 3 K⁺ içeri alır",
                    "3 K⁺ dışarı çıkarır, 2 Na⁺ içeri alır",
                    "İyonları enerji harcamadan taşır",
                ],
                "Sodyum-potasyum pompası, her ATP kullanımında hücre dışına 3 sodyum iyonu çıkarıp hücre içine 2 potasyum iyonu alır.",
                "Pompa aktif taşımadır: ATP harcar; sayılar sıkça karıştırılır (3 Na⁺ dışarı, 2 K⁺ içeri).",
                "hard",
            ),
            tf(
                "Kolaylaştırılmış difüzyonda taşıyıcı protein kullanıldığı için hücre ATP harcar.",
                False,
                "Kolaylaştırılmış difüzyonda glikoz gibi moleküller taşıyıcı proteinler yardımıyla zardan geçer, ancak yine de enerji harcanmaz.",
                "Taşıyıcı protein kullanılması enerji harcandığı anlamına gelmez; kolaylaştırılmış difüzyon pasif taşımadır.",
                "medium",
            ),
            cloze(
                "Hipertonik ortamdaki bitki hücresinin sitoplazmasının çeperden ayrılmasına ____ denir.",
                "plazmoliz",
                "Hipertonik bir ortama konan bitki hücresi su kaybeder ve sitoplazması çeperden ayrılır; bu olaya plazmoliz denir.",
                "Su kaybeden hücrede sitoplazma büzülür ve çeperden ayrılır: plazmoliz.",
            ),
            open_q(
                "Hipotonik ortamda bitki ve hayvan hücrelerinin farklı davranmasının nedenini açıklayınız.",
                "Bitki hücresi su alıp şişer ama çeperi patlamasını engeller; hayvan hücresinde çeper olmadığı için hücre patlayabilir.",
                [
                    "Hipotonik ortamda hücre su alarak şişer",
                    "Hücre çeperi bitki hücresinin patlamasını engeller",
                    "Hayvan hücrelerinde çeper olmadığı için patlayabilirler",
                ],
                "Hayvan hücreleri çepere sahip olmadığı için hipotonik ortamda patlayabilir.",
                "Fark hücre çeperinden kaynaklanır: çeper bitki hücresini mekanik olarak korur.",
            ),
            mcq(
                "Salgı proteinlerinin üretiminde görev alan yapı hangisidir?",
                [
                    "Granüllü endoplazmik retikulum",
                    "Granülsüz endoplazmik retikulum",
                    "Lizozom",
                    "Sentrozom",
                ],
                "Granüllü endoplazmik retikulumun yüzeyinde ribozomlar bulunur ve bu yapı salgı proteinlerinin üretiminde görev alır.",
                "Granülsüz ER lipit sentezinde görev alır; granüllü ER yüzeyindeki ribozomlar sayesinde protein üretir.",
            ),
            mcq(
                "Mitokondrinin kendini eşleyebilmesini sağlayan özellik hangisidir?",
                [
                    "Kendine ait DNA'sı ve ribozomlarının olması",
                    "Çift katlı zarının olması",
                    "ATP üretmesi",
                    "Oksijenli solunum yapması",
                ],
                "Mitokondrinin kendine ait DNA'sı ve ribozomları vardır, bu nedenle kendini eşleyebilir.",
                "Kendini eşleme için kalıtım materyali ve protein sentezi gerekir: DNA + ribozom.",
            ),
            tf(
                "Sentrozom bitki hücrelerinde bulunmaz.",
                True,
                "Bitki hücrelerinde sentrozom bulunmaz.",
                "Sentrozom hayvan hücrelerinde iğ ipliklerinin oluşumunu sağlar; bitki hücrelerinde yoktur.",
            ),
            open_q(
                "Pasif taşıma ile aktif taşımayı enerji kullanımı ve yön bakımından karşılaştırınız.",
                "Pasif taşımada enerji harcanmaz ve madde çok yoğundan az yoğuna gider; aktif taşımada ATP harcanır ve madde az yoğundan çok yoğuna taşınabilir.",
                [
                    "Pasif taşımada enerji harcanmaz",
                    "Pasif taşımada madde çok yoğundan az yoğuna geçer",
                    "Aktif taşımada ATP harcanır ve madde az yoğundan çok yoğuna taşınabilir",
                ],
                "Aktif taşımada ise hücre ATP harcar ve maddeler az yoğun ortamdan çok yoğun ortama taşınabilir.",
                "Enerji ve yön birlikte düşünülmeli: yoğunluk farkına karşı taşıma enerji ister.",
            ),
        ],
    },
    "tr_newton_yasalari": {
        "title": "Fizik 9 — Newton'un Hareket Yasaları",
        "questions": [
            mcq(
                "1 newton'luk kuvvet, 1 kg kütleli bir cisme ne kadar ivme kazandırır?",
                ["1 m/s²", "9,8 m/s²", "0,1 m/s²", "10 m/s²"],
                "Bir newton, 1 kilogram kütleli bir cisme 1 m/s² ivme kazandıran kuvvettir.",
                "Newton tanımı gereği 1 N = 1 kg · 1 m/s²; 9,8 m/s² yer çekimi ivmesidir ve sık karıştırılır.",
                "easy",
            ),
            cloze(
                "Cisimlerin hareket durumlarını koruma eğilimine ____ denir.",
                "eylemsizlik",
                "Cisimlerin hareket durumlarını koruma eğilimine eylemsizlik denir.",
                "Birinci yasa eylemsizlik yasası olarak da bilinir.",
            ),
            tf(
                "Eylemsizliğin ölçüsü kütledir.",
                True,
                "Eylemsizliğin ölçüsü kütledir; kütlesi büyük olan cismin eylemsizliği de büyüktür.",
                "Kütle arttıkça cismin hareket durumunu değiştirmek zorlaşır.",
            ),
            mcq(
                "Aniden fren yapan bir otobüste yolcuların öne savrulmasının nedeni nedir?",
                [
                    "Önceki hareket durumlarını koruma eğilimleri",
                    "Yolcuları öne iten bir kuvvet",
                    "Otobüsün yolculara uyguladığı tepki kuvveti",
                    "Sürtünme kuvvetinin aniden artması",
                ],
                "Burada yolcuları öne iten bir kuvvet yoktur; yolcular sadece önceki hareket durumlarını korumaya çalışır.",
                "Yaygın yanılgı öne iten bir kuvvet olduğunu düşünmektir; aslında yolcular eylemsizlik nedeniyle hareketlerini sürdürür.",
            ),
            mcq(
                "Net kuvvet sabit tutulurken kütle iki katına çıkarılırsa ivme nasıl değişir?",
                ["Yarıya iner", "İki katına çıkar", "Değişmez", "Dört katına çıkar"],
                "Net kuvvet sabit tutulduğunda kütle iki katına çıkarılırsa ivme yarıya iner.",
                "F = m · a; F sabitken m ile a ters orantılıdır.",
                "medium",
            ),
            tf(
                "Bir cismin Ay'daki kütlesi, Dünya'daki kütlesinin yaklaşık altıda biridir.",
                False,
                "Ay'daki yer çekimi ivmesi Dünya'dakinin yaklaşık altıda biri olduğundan, bir cismin Ay'daki ağırlığı Dünya'dakinin yaklaşık altıda biridir; kütlesi ise değişmez.",
                "Altıda birine inen ağırlıktır; kütle madde miktarıdır ve yerden yere değişmez.",
                "medium",
            ),
            open_q(
                "Etki ve tepki kuvvetleri neden birbirini dengelemez? Masadaki kitap örneğiyle açıklayınız.",
                "Etki ve tepki farklı cisimlere etki ettiği için dengelemez. Kitabın ağırlığı ile masanın tepkisi aynı cisme etki ettiği için etki-tepki çifti değildir.",
                [
                    "Etki ve tepki kuvvetleri farklı cisimlere etki eder",
                    "Bu yüzden birbirlerini dengelemezler",
                    "Kitabın ağırlığı ile masanın tepki kuvveti aynı cisme etki ettiği için etki-tepki çifti değildir",
                ],
                "Etki ve tepki kuvvetleri farklı cisimlere etki ettiği için birbirini dengelemez.",
                "Dengelenme için kuvvetlerin aynı cisme etki etmesi gerekir.",
            ),
            tf(
                "Sürtünme kuvveti, temas yüzeyinin alanı arttıkça artar.",
                False,
                "Sürtünme kuvveti yüzeylerin cinsine ve cismin yüzeye uyguladığı dik kuvvete bağlıdır, ancak temas yüzeyinin alanına bağlı değildir.",
                "Sürtünme yüzey cinsine ve dik kuvvete bağlıdır; temas alanına bağlı değildir.",
                "medium",
            ),
        ],
    },
    "en_supply_demand": {
        "title": "Microeconomics — Supply, Demand & Equilibrium",
        "questions": [
            mcq(
                "What does a change in a good's own price cause?",
                [
                    "A movement along the demand curve",
                    "A shift of the whole demand curve",
                    "A change in demand",
                    "A shift of the supply curve",
                ],
                "A change in the good's own price causes a movement along the demand curve, which economists call a change in quantity demanded.",
                "Only other determinants (income, tastes...) shift the curve; own price moves along it.",
                "easy",
            ),
            mcq(
                "Which of these is given as an example of an inferior good?",
                ["Bus travel", "Coffee", "Cars", "Tea"],
                "For an inferior good, an increase in income decreases demand; bus travel is a common example.",
                "As income rises people switch away from bus travel, so its demand falls.",
            ),
            tf(
                "Cars and gasoline are substitutes.",
                False,
                "Two goods are complements when a rise in the price of one decreases the demand for the other, such as cars and gasoline.",
                "They are complements; coffee and tea are the substitutes in the notes.",
            ),
            cloze(
                "If the price is above equilibrium, quantity supplied exceeds quantity demanded and a ____ arises.",
                "surplus",
                "If the price is above equilibrium, quantity supplied exceeds quantity demanded and a surplus arises, which pushes the price down.",
                "Excess supply is a surplus; excess demand is a shortage.",
            ),
            mcq(
                "Supply increases while demand is unchanged. What happens to the equilibrium?",
                [
                    "Price falls and quantity rises",
                    "Price and quantity both rise",
                    "Price rises and quantity falls",
                    "Price and quantity both fall",
                ],
                "When supply increases while demand is unchanged, the equilibrium price falls and the equilibrium quantity rises.",
                "A rightward supply shift moves down along the demand curve.",
                "medium",
            ),
            mcq(
                "When demand is inelastic, a price increase…",
                [
                    "raises total revenue",
                    "lowers total revenue",
                    "leaves total revenue unchanged",
                    "shifts the demand curve left",
                ],
                "When demand is inelastic, a price increase raises total revenue.",
                "Quantity falls proportionally less than price rises, so revenue goes up.",
                "hard",
            ),
            open_q(
                "Explain why a binding price ceiling creates a shortage, and give the example from the notes.",
                "A binding ceiling is set below the equilibrium price, so quantity demanded exceeds quantity supplied: a shortage. Rent control is the classic example.",
                [
                    "A binding price ceiling is set below the equilibrium price",
                    "It causes a shortage",
                    "Rent control is an example",
                ],
                "A binding price ceiling is set below the equilibrium price and causes a shortage; rent control is a classic example.",
                "Ceilings bind only below equilibrium; floors bind above it and create surpluses.",
            ),
            tf(
                "Demand tends to be more elastic over longer time horizons.",
                True,
                "Demand tends to be more elastic for goods with close substitutes, for luxuries rather than necessities, for narrowly defined markets and over longer time horizons.",
                "Given more time, buyers find substitutes and adjust their habits.",
            ),
        ],
    },
}

TOPIC_RE = re.compile(r"^#{2}\s*\d*\.?\s*(.+)$", re.M)


def _router(db: Database, doc_key: str) -> Router:
    pool = DEMO[doc_key]["questions"]

    def gen(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        if "topic map" in system:
            topics: list[dict[str, Any]] = []
            for cid in re.findall(r"^\[(\d+)\]", user, re.M):
                text = (db.one("SELECT text FROM chunks WHERE id=?", (int(cid),)) or {"text": ""})[
                    "text"
                ]
                heads = TOPIC_RE.findall(text)
                if heads:
                    for h in heads:
                        topics.append(
                            {
                                "title": h.strip(),
                                "summary": "",
                                "chunk_ids": [],
                                "misconceptions": [],
                            }
                        )
                    topics[-len(heads)]["chunk_ids"].append(int(cid))
                else:
                    if not topics:
                        topics.append(
                            {"title": "Giriş", "summary": "", "chunk_ids": [], "misconceptions": []}
                        )
                    topics[-1]["chunk_ids"].append(int(cid))
            return {"topics": topics}
        excerpt = normalize(user.split('"""')[1])
        return {"questions": [q for q in pool if normalize(q["source_quote"]) in excerpt]}

    def aud(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        qs = json.loads(user.split("QUESTIONS:\n", 1)[1])
        return {
            "items": [
                {
                    "index": q["index"],
                    "answer_supported": True,
                    "single_correct": True,
                    "distractors_ok": True,
                    "in_scope": True,
                    "language_ok": True,
                    "distractor_quality": 4,
                    "issues": [],
                    "verdict": "keep",
                    "fix_instructions": "",
                }
                for q in qs
            ]
        }

    return Router(
        {
            "generator": [FakeProvider(gen, "demo", "scripted")],
            "auditor": [FakeProvider(aud, "demo", "scripted-audit")],
        },
        db=db,
        use_cache=False,
    )


def simulate_history(db: Database, days: int = 48, seed: int = 3) -> int:
    """Simulated, clearly-demo review history so heatmap/streak/mastery have something to show."""
    rng = random.Random(seed)
    qs = db.all(
        "SELECT q.id, q.topic_id, q.difficulty, t.title FROM questions q JOIN topics t ON t.id=q.topic_id"
    )
    weak = {
        t for t in {q["title"] for q in qs} if any(k in t for k in ("Madde", "Etki", "Elasticity"))
    }
    sched = scheduler()
    today = datetime.now(UTC).replace(hour=17, minute=0, second=0, microsecond=0)
    n = 0
    introduced: list[dict[str, Any]] = []
    pending = qs[:]
    rng.shuffle(pending)
    for d in range(days, 0, -1):
        if rng.random() < 0.22 and d > 7:
            continue  # rest day
        at = today - timedelta(days=d, minutes=rng.randint(0, 300))
        for _ in range(rng.randint(1, 3)):
            if pending:
                introduced.append(pending.pop())
        for q in introduced:
            card = load_card(db, q["id"])
            if card.last_review is not None and card.due > at:
                continue
            p = 0.55 if q["title"] in weak else 0.86
            ok = rng.random() < p
            rating = Rating.Good if ok else Rating.Again
            if ok and rng.random() < 0.2:
                rating = Rating.Easy
            card, _ = sched.review_card(card, rating, review_datetime=at)
            ts = at.timestamp()
            with db.tx() as c:
                c.execute(
                    "UPDATE cards SET state=?, due=?, introduced_at=COALESCE(introduced_at, ?) WHERE question_id=?",
                    (json.dumps(card.to_dict()), card.due.timestamp(), ts, q["id"]),
                )
                c.execute(
                    "INSERT INTO reviews(question_id, rating, correct, score, response, duration_ms, mode, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        q["id"],
                        int(rating),
                        int(ok),
                        1.0 if ok else 0.0,
                        '"demo"',
                        rng.randint(3000, 20000),
                        "demo",
                        ts,
                    ),
                )
            n += 1
            at += timedelta(seconds=rng.randint(20, 90))
    return n


def seed(db: Database) -> dict[str, Any]:
    s = get_settings()
    s.chunk_chars = 900
    out: dict[str, Any] = {}
    for key, spec in DEMO.items():
        path = EVAL_DATA / f"{key}.md"
        svc = Service(db, s, _router(db, key))
        res = svc.add_file(path.name, path, "text", title=spec["title"])
        svc.ingest_document(res["id"])
        summary = Pipeline(db, svc.router, s).run(res["id"])
        meta = {"summary": summary, "demo": True}
        db.execute(
            "UPDATE documents SET status='ready', meta=? WHERE id=?",
            (json.dumps(meta, ensure_ascii=False), res["id"]),
        )
        db.execute("UPDATE jobs SET status='done', progress=1 WHERE status='queued'")
        out[key] = summary
    out["reviews"] = simulate_history(db)
    e = exam.create_exam(db, count=10, minutes=15, seed=5)
    qs = {q["id"]: q for q in db.all("SELECT id, type, correct_index, answer FROM questions")}
    answers: dict[str, Any] = {}
    for i, qid in enumerate(e["question_ids"]):
        q = qs[qid]
        good = i % 4 != 1
        if q["type"] == "mcq":
            answers[str(qid)] = q["correct_index"] if good else (q["correct_index"] + 1) % 4
        elif q["type"] == "tf":
            answers[str(qid)] = q["answer"] == "true" if good else q["answer"] != "true"
        elif q["type"] == "cloze":
            answers[str(qid)] = q["answer"] if good else "?"
    exam.submit_exam(db, e["id"], answers)
    db.execute(
        "UPDATE exams SET started_at=?, finished_at=? WHERE id=?",
        (now() - 86400 * 2, now() - 86400 * 2 + 640, e["id"]),
    )
    return out
