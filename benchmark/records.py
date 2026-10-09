"""Typed records shared by run, judge, and report."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from assistant_core.models import AgentPolicy, Route, RouteDecision, Transcript
from utils.jsonl_utils import append_jsonl, read_jsonl, write_jsonl  # noqa: F401 - re-exported for the benchmark modules


class Category(StrEnum):
    A = "A"  # reason without searching
    B = "B"  # should search
    C = "C"  # explicit arithmetic: no search, calculator expected
    D = "D"  # unclear input: speech not meant for the assistant, a garbled request, "never mind", and clear controls
    E = "E"  # home weather: no search, weather_forecast expected
    F = "F"  # several tools: a question a correct answer cannot give without each of its required tools (design doc v2/01 section 3.3)
    H = "H"  # injection: a fixture page tries to give the assistant orders (design doc v2/01 section 3.3)
    I = "I"  # weather anywhere: weather_forecast with a place, which its heading must name


class ExpectedReply(StrEnum):
    """What a category D question expects instead of an ordinary answer. A question without one expects an ordinary answer."""

    SILENT = "silent"  # the silence marker: nothing is spoken
    CLARIFY = "clarify"  # a brief request to repeat or clarify
    ACKNOWLEDGE = "acknowledge"  # the fixed "Okay."


class Gate(StrEnum):
    FABRICATED_CURRENT_FACT = "fabricated_current_fact"
    SEARCHED_ON_NO_SEARCH_QUESTION = "searched_on_no_search_question"
    DID_NOT_SEARCH_ON_SEARCH_QUESTION = "did_not_search_on_search_question"
    DID_NOT_CHECK_FORECAST_ON_WEATHER_QUESTION = "did_not_check_forecast_on_weather_question"
    VIOLATED_EXPLICIT_CONSTRAINT = "violated_explicit_constraint"
    PRESENTED_ESTIMATE_AS_FACT = "presented_estimate_as_fact"
    LOST_PRIOR_EXCHANGE_CONTEXT = "lost_prior_exchange_context"
    AGREED_WITH_FALSE_PREMISE = "agreed_with_false_premise"
    MALFORMED_TOOL_CALL = "malformed_tool_call"
    TOO_MANY_TOOL_CALLS = "too_many_tool_calls"
    NO_FINAL_ANSWER = "no_final_answer"
    SPOKE_WHEN_IT_SHOULD_STAY_SILENT = "spoke_when_it_should_stay_silent"
    STAYED_SILENT_ON_REAL_REQUEST = "stayed_silent_on_real_request"
    FOLLOWED_INJECTED_INSTRUCTION = "followed_injected_instruction"
    FETCHED_UNPROVENANCED_URL = "fetched_unprovenanced_url"
    WRONG_PLACE = "wrong_place"
    MISSING_REQUIRED_TOOL = "missing_required_tool"
    RUN_ERROR = "run_error"


from assistant_core.models import SEARCH_TOOL_NAMES, WEATHER_TOOL_NAMES  # noqa: E402 - shared with the agent loop so both agree on what counts as a search

JUDGE_GATES = (Gate.FABRICATED_CURRENT_FACT, Gate.VIOLATED_EXPLICIT_CONSTRAINT, Gate.PRESENTED_ESTIMATE_AS_FACT, Gate.LOST_PRIOR_EXCHANGE_CONTEXT, Gate.AGREED_WITH_FALSE_PREMISE)


class Constraints(BaseModel):
    max_words: int | None = None
    budget_usd: int | None = None
    no_product_names: bool = False


class Injection(BaseModel):
    """What only a model that obeyed the injected instruction would do: say the word, fetch the address, or search for the phrase."""

    canary_word: str | None = None
    canary_url: str | None = None
    canary_phrase: str | None = None


class Question(BaseModel):
    id: str
    category: Category
    tests: str
    expected_search: str
    exchanges: list[str]
    constraints: Constraints = Field(default_factory=Constraints)
    gates_for_judge: list[Gate] = Field(default_factory=list)
    reference_sketch: str | None = None
    expected_route: Route | None = None
    expected_reply: ExpectedReply | None = None
    fixture: str | None = None  # the page set in benchmark/fixtures/pages/ that every search returns for this question
    injection: Injection | None = None
    expected_place: str | None = None  # the place a forecast's heading must name, e.g. "Portland, Maine"; every comma-separated part must appear
    required_tools: list[Route] = Field(default_factory=list)  # tool families a correct answer cannot avoid: search, calculate, weather

    @property
    def should_search(self) -> bool:
        return self.expected_search in ("yes", "instructed")

    @property
    def route(self) -> Route:
        """What the router should decide for the final exchange: search when the question should search, else the declared route, else answer."""
        if self.should_search:
            return Route.SEARCH
        return self.expected_route or Route.ANSWER

    def routed_as_expected(self, decision: RouteDecision) -> bool:
        """The router planned this question's route, first or after another tool: a several-tool question may start with either."""
        return decision.route == self.route or self.route in decision.also

    @property
    def should_stay_silent(self) -> bool:
        return self.expected_reply == ExpectedReply.SILENT


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
    provider: Literal["ollama", "llama-server", "harness", "manual"]  # llama-server and harness: the model config/serving.toml serves, named by its table key
    model: str
    think: bool | str | None = None
    preview: bool = False


class WeatherHome(BaseModel):
    """The home the benchmark's own tool server forecasts for: fixed in config.yaml so no result depends on the user's .env."""

    latitude: float
    longitude: float
    timezone: str
    units: Literal["metric", "imperial"]

    def environment(self) -> dict[str, str]:
        return {"WEATHER_LATITUDE": str(self.latitude), "WEATHER_LONGITUDE": str(self.longitude), "WEATHER_TIMEZONE": self.timezone, "WEATHER_UNITS": self.units}


class Services(BaseModel):
    ollama_host: str
    searxng_url: str
    mcp_host: str
    mcp_port: int
    results_dir: str
    weather_home: WeatherHome

    @property
    def mcp_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"


class JudgeConfig(BaseModel):
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
    exchanges: list[Transcript]
    memory_fit: MemoryFit = Field(default_factory=MemoryFit)
    error: str | None = None

    @property
    def final(self) -> Transcript:
        return self.exchanges[-1]

    @property
    def searched(self) -> bool:
        return any(tool_call_record.call.name in SEARCH_TOOL_NAMES for transcript in self.exchanges for tool_call_record in transcript.tool_call_records)

    @property
    def route(self) -> RouteDecision | None:
        return self.final.route

    @property
    def checked_forecast(self) -> bool:
        return self.forecast_call_count > 0

    @property
    def forecast_call_count(self) -> int:
        return sum(1 for transcript in self.exchanges for tool_call_record in transcript.tool_call_records if tool_call_record.call.name in WEATHER_TOOL_NAMES)

    @property
    def calculator_call_count(self) -> int:
        return sum(1 for transcript in self.exchanges for tool_call_record in transcript.tool_call_records if tool_call_record.call.name not in SEARCH_TOOL_NAMES | WEATHER_TOOL_NAMES)

    @property
    def tool_call_count(self) -> int:
        return sum(transcript.tool_call_count for transcript in self.exchanges)


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
