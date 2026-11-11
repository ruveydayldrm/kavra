"""Prompt templates. Instructions are English (models follow them best); output language is
set explicitly per document."""

from __future__ import annotations

import json

LANG_NAME = {"tr": "Turkish (Türkçe)", "en": "English"}


def lang_name(lang: str) -> str:
    return LANG_NAME.get(lang, lang)


TOPIC_SYSTEM = """You organise course material into a study topic map.
Rules:
- Group the numbered excerpts into 3-12 coherent topics in reading order (fewer for short material).
- Every excerpt id must appear in exactly one topic.
- Titles are short noun phrases a student would recognise; no numbering.
- misconceptions: concrete, topic-specific mistakes students make (e.g. confusing X with Y),
  not generic advice. They will be used as distractors, so they must be wrong per the material.
- Write all text in {lang}. Return JSON only."""


def topic_user(excerpts: list[tuple[int, str]], title: str) -> str:
    lines = [f"Material: {title}", "", "Excerpts (id: beginning of text):"]
    for cid, text in excerpts:
        lines.append(f"[{cid}] {text[:350].replace(chr(10), ' ')}")
    return "\n".join(lines)


GEN_SYSTEM = """You are an expert exam writer creating study questions from ONE excerpt of course material.

Hard rules (a question that breaks any of them will be discarded):
1. Use ONLY facts stated in the excerpt. No outside knowledge, no inference beyond the text.
2. source_quote must be copied VERBATIM (character for character) from the excerpt and must,
   on its own, prove the correct answer. Keep it to 1-2 sentences.
3. Exactly one defensible answer. Avoid "all/none of the above", double negatives, trick wording.
4. mcq: exactly 4 options, similar length and grammar, correct_index points to the right one,
   answer = that option's text. Wrong options must be plausible to a student who half-learned
   the topic and clearly wrong per the excerpt. Build them from the listed common
   misconceptions and from confusable terms in the excerpt.
5. tf: answer is "true" or "false"; false statements must change one meaningful detail.
6. cloze: one blank written as ____ hiding a key term that appears in source_quote.
7. open: ask for an explanation/comparison; key_points = 2-5 atomic facts from the excerpt.
8. Test understanding, not trivia (no page numbers, author names or formatting details).
9. Mix types and difficulties. easy = recall, medium = understand/apply, hard = connect/contrast.
10. Write everything in {lang}. Return JSON only."""


def gen_user(excerpt: str, topic: str, misconceptions: list[str], n: int, avoid: list[str]) -> str:
    parts = [
        f"Topic: {topic}",
        "Common misconceptions for this topic: " + ("; ".join(misconceptions) or "(none listed)"),
        f"Write {n} questions. Suggested mix: mcq, tf, cloze, open (at least half mcq).",
    ]
    if avoid:
        parts.append("Do NOT repeat these existing questions:\n- " + "\n- ".join(avoid[:12]))
    parts += ["", "EXCERPT:", '"""', excerpt, '"""']
    return "\n".join(parts)


AUDIT_SYSTEM = """You are a strict exam quality reviewer. You did NOT write these questions.
For each question, check against the excerpt only:
- answer_supported: the excerpt explicitly supports the stated correct answer.
- single_correct: exactly one option/answer is defensible; no other option is also correct.
- distractors_ok (mcq): every wrong option is plausible but definitely wrong per the excerpt.
- in_scope: answerable from the excerpt alone.
- language_ok: natural, grammatical {lang}; unambiguous.
- distractor_quality: 1 (silly/obvious) .. 5 (targets a real misconception).
verdict: "keep" if everything holds; "fix" if a small edit would make it valid (say exactly
what in fix_instructions); "drop" if the answer is not supported, it needs outside knowledge,
or it is trivial. Be strict: when in doubt between keep and fix, choose fix. Return JSON only."""


def audit_user(excerpt: str, questions: list[dict[str, object]]) -> str:
    view = []
    for i, q in enumerate(questions):
        view.append(
            {
                "index": i,
                "type": q["type"],
                "stem": q["stem"],
                "options": q["options"],
                "correct": q["answer"],
                "key_points": q["key_points"],
                "explanation": q["explanation"],
            }
        )
    return (
        'EXCERPT:\n"""\n'
        + excerpt
        + '\n"""\n\nQUESTIONS:\n'
        + json.dumps(view, ensure_ascii=False, indent=1)
    )


REPAIR_SYSTEM = """You fix a single exam question so that it passes review.
Apply the reviewer's instructions, keep everything else, obey all rules:
answer only from the excerpt, verbatim source_quote, exactly one correct answer, 4 options for mcq.
Write in {lang}. Return JSON with a "questions" array containing exactly one question."""


def repair_user(excerpt: str, question: dict[str, object], instructions: str) -> str:
    return (
        'EXCERPT:\n"""\n'
        + excerpt
        + '\n"""\n\nQUESTION:\n'
        + json.dumps(question, ensure_ascii=False, indent=1)
        + "\n\nREVIEWER INSTRUCTIONS:\n"
        + instructions
    )


GRADE_SYSTEM = """You grade a student's short answer against key points from the course material.
A key point is covered only if the answer states it correctly (paraphrase is fine).
Feedback: one or two encouraging sentences in {lang} naming what is missing or wrong. JSON only."""
