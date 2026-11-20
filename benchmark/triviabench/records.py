"""TriviaBench's typed records: the question set, the closed-book reference answers, and one result per question per candidate."""

from enum import IntEnum, StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

from assistant_core.models import SEARCH_TOOL_NAMES, Transcript


class Topic(StrEnum):
    LITERATURE = "Literature"
    SPORTS = "Sports"
    MATH = "Math"
    SCIENCE = "Science"
    HISTORY = "History"
    FINANCE = "Finance"
    POLITICS = "Politics"
    MUSIC = "Music"
    ENTERTAINMENT = "Entertainment"
    MISC = "Misc"


class Era(StrEnum):
    """The period a question is about, from its year of relevance. TIMELESS: no particular year, such as a capital city or a word's meaning."""

    BEFORE_1500 = "before 1500"
    FROM_1500_TO_1799 = "1500-1799"
    FROM_1800_TO_1899 = "1800-1899"
    FROM_1900_TO_1949 = "1900-1949"
    FROM_1950_TO_1979 = "1950-1979"
    FROM_1980_TO_1999 = "1980-1999"
    SINCE_2000 = "2000 on"
    TIMELESS = "timeless"


class Difficulty(IntEnum):
    """How obscure the fact is for a well-read adult, as Claude Opus 5.5 labelled it when the set was built."""

    EASY = 1  # most adults in the UK or US would know it
    MEDIUM = 2  # a regular pub-quiz player would likely know it
    HARD = 3  # specialist or obscure


class TriviaSize(StrEnum):
    XS = "xs"  # 100 questions, every one also in S
    S = "s"  # 1,000 questions


class TriviaQuestion(BaseModel):
    id: str
    triviaqa_id: str
    question: str
    answers: list[str]  # the TriviaQA value first, then its aliases
    topic: Topic
    year: int | None  # negative for BC; None when no year applies
    era: Era
    difficulty: Difficulty
    in_xs: bool


class TriviaSet(BaseModel):
    version: str
    search_instruction: str  # appended to every question so the model searches instead of answering from memory
    questions: list[TriviaQuestion]

    def of_size(self, size: TriviaSize) -> list[TriviaQuestion]:
        return [question for question in self.questions if question.in_xs or size == TriviaSize.S]

    def by_id(self, question_id: str) -> TriviaQuestion:
        return next(question for question in self.questions if question.id == question_id)

    def spoken_question(self, question: TriviaQuestion) -> str:
        return f"{question.question} {self.search_instruction}"


def load_trivia_set(path: Path) -> TriviaSet:
    return TriviaSet(**yaml.safe_load(path.read_text()))


class ReferenceAnswer(BaseModel):
    question_id: str
    answer: str
    reviewed_correct: bool  # the verdict after a person-style review of every miss, which the alias grader cannot reproduce


class ReferenceAnswers(BaseModel):
    answered_by: str
    method: str
    answers: list[ReferenceAnswer]


def load_reference_answers(path: Path) -> ReferenceAnswers:
    return ReferenceAnswers(**yaml.safe_load(path.read_text()))


class TriviaResult(BaseModel):
    question_id: str
    candidate_key: str
    model: str
    transcript: Transcript | None = None
    error: str | None = None

    @property
    def answer(self) -> str:
        return self.transcript.final_answer if self.transcript else ""

    @property
    def search_queries(self) -> list[str]:
        if self.transcript is None:
            return []
        return [str(record.call.arguments.get("query", "")) for record in self.transcript.tool_call_records if record.call.name in SEARCH_TOOL_NAMES]

    @property
    def searched(self) -> bool:
        return bool(self.search_queries)
