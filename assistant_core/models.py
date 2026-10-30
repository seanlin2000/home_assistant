from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Route(StrEnum):
    SEARCH = "search"
    CALCULATE = "calculate"
    WEATHER = "weather"
    SPORTS = "sports"
    SHOWS = "shows"
    MOVIES = "movies"
    REDDIT = "reddit"
    ANSWER = "answer"


class RouteDecision(BaseModel):
    """What the router decided before the model spoke: which tool family the question needs first, any it needs as well, and which layer decided it."""

    route: Route
    source: str  # "rule", "model", or "none"
    detail: str = ""
    seconds: float = 0.0
    also: list[Route] = Field(default_factory=list)  # further tool families, in the order to use them (design doc v2/04 section 3.3)
    plan: str = ""  # one sentence on how the tools fit together, when there is more than one
    started_seconds: float | None = None  # from the start of the exchange; None in records written before it was kept

    @property
    def tool_routes(self) -> list[Route]:
        """Every tool family the question needs, first one first; empty for a question answered without tools."""
        return [route for route in (self.route, *self.also) if route != Route.ANSWER]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Role
    content: str = ""
    thinking: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class AgentPolicy(BaseModel):
    temperature: float = 0.7
    max_tool_rounds: int = 4
    max_output_tokens: int = 600
    word_budget: int = 200
    context_tokens: int = 16384
    think: bool | str | None = None
    route_questions: bool = True
    filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_FILLER_PHRASES))
    calculate_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_CALCULATE_FILLER_PHRASES))
    weather_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_WEATHER_FILLER_PHRASES))
    sports_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_SPORTS_FILLER_PHRASES))
    shows_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_SHOWS_FILLER_PHRASES))
    movies_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_MOVIES_FILLER_PHRASES))
    reddit_filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_REDDIT_FILLER_PHRASES))
    reddit_still_trying_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_REDDIT_STILL_TRYING_PHRASES))
    reddit_unavailable_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_REDDIT_UNAVAILABLE_PHRASES))
    still_trying_after_seconds: float = 6.0  # a Reddit call still running this long is most likely retrying, so the user hears why it is slow
    tool_timeout_seconds: float = 30.0
    history_exchanges: int = Field(default=3, ge=0)  # earlier exchanges replayed with each question; more and the model answers from the history instead of looking up

    @property
    def every_filler_phrase(self) -> list[str]:
        return [
            *self.filler_phrases,
            *self.calculate_filler_phrases,
            *self.weather_filler_phrases,
            *self.sports_filler_phrases,
            *self.shows_filler_phrases,
            *self.movies_filler_phrases,
            *self.reddit_filler_phrases,
            *self.reddit_still_trying_phrases,
            *self.reddit_unavailable_phrases,
        ]


# Spoken while the first tool call of an exchange runs, so the user hears something within a second or two. Search, calculation, the forecast,
# sports, and show listings get different lines because "checking the web" is wrong, and mildly alarming, when the assistant is doing arithmetic
# locally or reading a forecast, a box score, or the night's listings.
DEFAULT_FILLER_PHRASES = (
    "Let me pull some sources on that.",
    "One moment, checking the web.",
    "Understood, let me look that up.",
)
DEFAULT_CALCULATE_FILLER_PHRASES = (
    "Let me work that out.",
    "One second, doing the math.",
)
DEFAULT_WEATHER_FILLER_PHRASES = (
    "Checking the forecast.",
    "One moment, getting the forecast.",
)
DEFAULT_SPORTS_FILLER_PHRASES = (
    "Let me check the numbers.",
    "One moment, pulling up the numbers.",
)
DEFAULT_SHOWS_FILLER_PHRASES = (
    "Let me check what's playing.",
    "One moment, pulling up the listings.",
)
DEFAULT_MOVIES_FILLER_PHRASES = (
    "Let me check what's in theaters.",
    "One moment, pulling up the movie listings.",
)
# Reddit is read through Arctic Shift, a free archive that times out under load, so the first line warns that it can be slow, a second line follows
# when the call is still running (most likely retrying), and a third replaces the silence when it never answered and the model searches the web instead.
DEFAULT_REDDIT_FILLER_PHRASES = (
    "Checking Reddit. It can be slow, but I'll do my best.",
    "Let me see what Reddit says. It can be slow, but I'll do my best.",
)
DEFAULT_REDDIT_STILL_TRYING_PHRASES = (
    "Reddit's slow today, still trying.",
    "Still waiting on Reddit, one more moment.",
)
DEFAULT_REDDIT_UNAVAILABLE_PHRASES = ("I couldn't reach Reddit, so I'll check the web instead.",)
SEARCH_TOOL_NAMES = frozenset({"search_and_read", "web_search", "fetch_page", "wikipedia_lookup"})
WEATHER_TOOL_NAMES = frozenset({"weather_forecast"})
SPORTS_TOOL_NAMES = frozenset({"game_scores", "box_score", "team_roster", "player_stats", "player_matchup"})
SHOWS_TOOL_NAMES = frozenset({"broadway_shows", "broadway_show_details"})
MOVIES_TOOL_NAMES = frozenset({"movies_showing", "movie_details"})
REDDIT_TOOL_NAMES = frozenset({"reddit_search"})
# How reddit_search's answer starts when Arctic Shift never answered, so the agent loop knows to say the could-not-reach line.
REDDIT_UNAVAILABLE_PREFIX = "Reddit error: Reddit did not answer"
# The router's JSON: a route, up to two more, and a one-sentence plan. Forty tokens held the route alone and cut the plan off mid-string.
CLASSIFY_MAX_TOKENS = 120
CALCULATOR_TOOL_NAMES = frozenset({"calculate", "percent", "convert", "growth_schedule", "energy_cost", "loan_payment", "break_even", "date_math"})
TOOL_NAMES_BY_ROUTE = {
    Route.SEARCH: SEARCH_TOOL_NAMES,
    Route.CALCULATE: CALCULATOR_TOOL_NAMES,
    Route.WEATHER: WEATHER_TOOL_NAMES,
    Route.SPORTS: SPORTS_TOOL_NAMES,
    Route.SHOWS: SHOWS_TOOL_NAMES,
    Route.MOVIES: MOVIES_TOOL_NAMES,
    Route.REDDIT: REDDIT_TOOL_NAMES,
}
# The tools a live tool server must expose before the benchmark or the health check trusts it as ours (a stale server once served a different set).
REQUIRED_TOOL_NAMES = frozenset({"search_and_read", "web_search", "fetch_page", "wikipedia_lookup", "calculate", "percent", "convert"})


class GenerationStats(BaseModel):
    model: str
    prompt_tokens: int | None = None
    fresh_prompt_tokens: int | None = None  # read from nothing on this request; the rest came from the prompt cache
    cached_prompt_tokens: int | None = None
    output_tokens: int | None = None
    time_to_first_token_seconds: float | None = None
    total_seconds: float
    prompt_eval_seconds: float | None = None
    generation_seconds: float | None = None
    load_seconds: float | None = None
    stop_reason: str | None = None
    slot: int | None = None  # the llama-server slot the request was pinned to; None on Ollama
    started_seconds: float | None = None  # from the start of the exchange; None in records written before it was kept


class TextDelta(BaseModel):
    text: str


class ToolCallRequest(BaseModel):
    call: ToolCall


class MalformedToolCall(BaseModel):
    raw: str


class Completion(BaseModel):
    message: Message
    stats: GenerationStats


LLMEvent = TextDelta | ToolCallRequest | MalformedToolCall | Completion


class FillerSpoken(BaseModel):
    text: str


class ToolStarted(BaseModel):
    call: ToolCall


class ToolFinished(BaseModel):
    call: ToolCall
    seconds: float
    error: str | None = None


class AnswerDelta(BaseModel):
    text: str


class ToolCallRecord(BaseModel):
    round_index: int
    call: ToolCall
    result: str
    seconds: float
    error: str | None = None
    refused: bool = False  # the guards stopped it before it ran; result holds the sentence the model read instead
    repeated: bool = False  # the same call ran earlier in this question; result is that call's result, not a new one
    started_seconds: float | None = None  # from the start of the exchange; None in records written before it was kept


class Transcript(BaseModel):
    model: str
    system_prompt: str
    conversation: list[Message]
    tool_call_records: list[ToolCallRecord] = Field(default_factory=list)
    model_calls: list[GenerationStats] = Field(default_factory=list)
    malformed_tool_calls: list[str] = Field(default_factory=list)
    spoken_text: str = ""
    filler_text: str = ""  # the phrase spoken while the first tools ran
    tool_notices: list[str] = Field(default_factory=list)  # lines spoken later in the exchange: Reddit still trying, Reddit not reached
    final_answer: str = ""
    truncated: bool = False
    tool_call_count: int = 0
    hit_tool_round_cap: bool = False
    empty_completion_retries: int = 0  # times the model returned neither text nor a tool call and was asked again
    malformed_retries: int = 0  # times the model's only output was a tool call that could not be parsed, and it was asked again without it
    stayed_silent: bool = False  # the final reply was the silence marker, so no answer was spoken
    total_seconds: float = 0.0
    time_to_first_token_seconds: float | None = None
    time_to_first_spoken_seconds: float | None = None
    route: RouteDecision | None = None
    untrusted: bool = False  # a tool whose text is written by strangers ran in this exchange (design doc v2/12 section 3.2)
    error: str | None = None


class Done(BaseModel):
    transcript: Transcript


AgentEvent = FillerSpoken | ToolStarted | ToolFinished | AnswerDelta | Done
