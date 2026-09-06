"""Typed records shared by run, judge, and report."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from assistant_core.models import AgentPolicy, Route, RouteDecision, Transcript


class Category(StrEnum):
    A = "A"  # reason without searching
    B = "B"  # should search
    C = "C"  # explicit arithmetic: no search, calculator expected


class Gate(StrEnum):
    FABRICATED_CURRENT_FACT = "fabricated_current_fact"
    SEARCHED_ON_NO_SEARCH_QUESTION = "searched_on_no_search_question"
    DID_NOT_SEARCH_ON_SEARCH_QUESTION = "did_not_search_on_search_question"
    VIOLATED_EXPLICIT_CONSTRAINT = "violated_explicit_constraint"
    PRESENTED_ESTIMATE_AS_FACT = "presented_estimate_as_fact"
    LOST_PRIOR_TURN_CONTEXT = "lost_prior_turn_context"
    AGREED_WITH_FALSE_PREMISE = "agreed_with_false_premise"
    MALFORMED_TOOL_CALL = "malformed_tool_call"
    TOO_MANY_TOOL_CALLS = "too_many_tool_calls"
    NO_FINAL_ANSWER = "no_final_answer"
    RUN_ERROR = "run_error"


SEARCH_TOOL_NAMES = frozenset({"search_and_read", "web_search", "fetch_page"})

JUDGE_GATES = (Gate.FABRICATED_CURRENT_FACT, Gate.VIOLATED_EXPLICIT_CONSTRAINT, Gate.PRESENTED_ESTIMATE_AS_FACT, Gate.LOST_PRIOR_TURN_CONTEXT, Gate.AGREED_WITH_FALSE_PREMISE)


class Constraints(BaseModel):
    max_words: int | None = None
    budget_usd: int | None = None
    no_product_names: bool = False


class Question(BaseModel):
    id: str
    category: Category
    tests: str
    expected_search: str
    turns: list[str]
    constraints: Constraints = Field(default_factory=Constraints)
    gates_for_judge: list[Gate] = Field(default_factory=list)
    reference_sketch: str | None = None
    expected_route: Route | None = None

    @property
    def should_search(self) -> bool:
        return self.expected_search in ("yes", "instructed")

    @property
    def route(self) -> Route:
        """What the router should decide for the final turn: search when the question should search, else the declared route, else answer."""
        if self.should_search:
            return Route.SEARCH
        return self.expected_route or Route.ANSWER


class QuestionSet(BaseModel):
    version: str
    questions: list[Question]

    def by_id(self, question_id: str) -> Question:
        return next(question for question in self.questions if question.id == question_id)


def load_questions(path: Path) -> QuestionSet:
    return QuestionSet(**yaml.safe_load(path.read_text()))


class Candidate(BaseModel):
    key: str
    label: str
    provider: str
    model: str
    think: bool | str | None = None
    effort: str | None = None
    preview: bool = False
    baseline: bool = False


class Services(BaseModel):
    ollama_host: str
    searxng_url: str
    mcp_host: str
    mcp_port: int
    results_dir: str

    @property
    def mcp_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"


class JudgeConfig(BaseModel):
    model: str
    concurrency: int = 4
    review_sample_fraction: float = 0.2
    review_seed: int = 0


class BenchmarkConfig(BaseModel):
    policy: AgentPolicy
    services: Services
    candidates: list[Candidate]
    judge: JudgeConfig

    def candidate(self, key: str) -> Candidate:
        return next(candidate for candidate in self.candidates if candidate.key == key)


def load_config(path: Path) -> BenchmarkConfig:
    return BenchmarkConfig(**yaml.safe_load(path.read_text()))


class MemoryFit(BaseModel):
    model_size_bytes: int | None = None
    gpu_resident_bytes: int | None = None
    fully_on_gpu: bool | None = None


class QuestionResult(BaseModel):
    question_id: str
    candidate_key: str
    model: str
    turns: list[Transcript]
    memory_fit: MemoryFit = Field(default_factory=MemoryFit)
    error: str | None = None

    @property
    def final(self) -> Transcript:
        return self.turns[-1]

    @property
    def searched(self) -> bool:
        return any(exchange.call.name in SEARCH_TOOL_NAMES for transcript in self.turns for exchange in transcript.tool_exchanges)

    @property
    def route(self) -> RouteDecision | None:
        return self.final.route

    @property
    def calculator_call_count(self) -> int:
        return sum(1 for transcript in self.turns for exchange in transcript.tool_exchanges if exchange.call.name not in SEARCH_TOOL_NAMES)

    @property
    def tool_call_count(self) -> int:
        return sum(transcript.tool_call_count for transcript in self.turns)


class JudgeVerdict(BaseModel):
    gates_hit: list[Gate] = Field(default_factory=list)
    search_decision_correct: bool
    answer_quality: int
    judgment: int
    spoken_fit: int
    answer_quality_reason: str
    judgment_reason: str
    spoken_fit_reason: str


class Score(BaseModel):
    question_id: str
    candidate_key: str
    category: Category
    harness_gates: list[Gate]
    judge: JudgeVerdict | None
    judge_model: str | None = None
    judge_error: str | None = None
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0

    @property
    def gates(self) -> list[Gate]:
        judge_gates = self.judge.gates_hit if self.judge else []
        return sorted(set(self.harness_gates) | set(judge_gates))

    @property
    def dimension_total(self) -> int:
        if self.judge is None:
            return 0
        return self.judge.answer_quality + self.judge.judgment + self.judge.spoken_fit

    @property
    def total(self) -> int:
        return 0 if self.gates else self.dimension_total

    @property
    def harness_and_judge_disagree(self) -> bool:
        if self.judge is None:
            return False
        harness_says_search_wrong = any(gate in (Gate.SEARCHED_ON_NO_SEARCH_QUESTION, Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION) for gate in self.harness_gates)
        return harness_says_search_wrong == self.judge.search_decision_correct


def write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def append_jsonl(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(record.model_dump_json() + "\n")


def read_jsonl(path: Path, record_type: type[BaseModel]) -> list[Any]:
    if not path.exists():
        return []
    return [record_type.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
