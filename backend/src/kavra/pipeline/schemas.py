"""Structured outputs exchanged with the models. Every LLM response is validated here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

QType = Literal["mcq", "tf", "cloze", "open"]
Difficulty = Literal["easy", "medium", "hard"]


class TopicDraft(BaseModel):
    title: str = Field(description="Short topic name, 2-6 words, in the material's language")
    summary: str = Field(description="One sentence describing what the topic covers")
    chunk_ids: list[int] = Field(description="Ids of the excerpts that belong to this topic")
    misconceptions: list[str] = Field(
        description="2-4 mistakes students commonly make about this topic (used for distractors)"
    )


class TopicMap(BaseModel):
    topics: list[TopicDraft]


class QuestionDraft(BaseModel):
    type: QType
    difficulty: Difficulty
    stem: str = Field(description="The question. For cloze use ____ for the single blank.")
    options: list[str] = Field(description="Exactly 4 options for mcq, else empty")
    correct_index: int = Field(description="0-3 for mcq, else -1")
    answer: str = Field(
        description="mcq: text of the correct option; tf: 'true' or 'false'; cloze: the blank word(s); open: a model answer"
    )
    accepted: list[str] = Field(
        description="cloze only: other accepted spellings/synonyms, else empty"
    )
    key_points: list[str] = Field(
        description="open only: 2-5 atomic points a full answer must contain, else empty"
    )
    explanation: str = Field(
        description="Why the answer is right (and, for mcq, why the traps are wrong)"
    )
    source_quote: str = Field(
        description="VERBATIM sentence(s) copied from the excerpt that prove the answer"
    )

    @field_validator("stem", "answer", "explanation", "source_quote")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class QuestionBatch(BaseModel):
    questions: list[QuestionDraft]


class AuditItem(BaseModel):
    index: int
    answer_supported: bool = Field(description="The excerpt clearly states the correct answer")
    single_correct: bool = Field(description="Exactly one defensible answer")
    distractors_ok: bool = Field(
        description="mcq: every wrong option is plausible yet definitely wrong per the excerpt; non-mcq: true"
    )
    in_scope: bool = Field(description="Answerable from the excerpt alone, no outside knowledge")
    language_ok: bool = Field(description="Grammatical, natural, unambiguous wording")
    distractor_quality: int = Field(description="1-5, mcq trap quality; 3 for non-mcq")
    issues: list[str] = Field(description="Concrete problems, empty if none")
    verdict: Literal["keep", "fix", "drop"]
    fix_instructions: str = Field(
        description="If verdict is fix: what exactly to change, else empty"
    )


class AuditReport(BaseModel):
    items: list[AuditItem]


class GradeResult(BaseModel):
    score: float = Field(description="0.0-1.0")
    covered: list[int] = Field(description="indexes of key points the answer covers")
    feedback: str = Field(description="One or two sentences: what is missing or wrong")
