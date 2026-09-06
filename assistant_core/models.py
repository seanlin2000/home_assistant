from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    # Raw provider content blocks for assistant turns. Anthropic requires thinking and tool_use blocks
    # to be echoed back unchanged on the next request, which a plain text field cannot carry.
    provider_payload: Any | None = None


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
    think: bool | None = None
    effort: str | None = None
    filler_phrases: list[str] = Field(default_factory=lambda: list(DEFAULT_FILLER_PHRASES))
    tool_timeout_seconds: float = 30.0


DEFAULT_FILLER_PHRASES = (
    "Let me pull some sources on that.",
    "One moment, checking the web.",
    "Understood, let me look that up.",
)


class GenerationStats(BaseModel):
    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    time_to_first_token_seconds: float | None = None
    total_seconds: float
    prompt_eval_seconds: float | None = None
    generation_seconds: float | None = None
    load_seconds: float | None = None
    stop_reason: str | None = None


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


class ToolExchange(BaseModel):
    round_index: int
    call: ToolCall
    result: str
    seconds: float
    error: str | None = None


class Transcript(BaseModel):
    model: str
    system_prompt: str
    conversation: list[Message]
    tool_exchanges: list[ToolExchange] = Field(default_factory=list)
    model_calls: list[GenerationStats] = Field(default_factory=list)
    malformed_tool_calls: list[str] = Field(default_factory=list)
    spoken_text: str = ""
    final_answer: str = ""
    truncated: bool = False
    tool_call_count: int = 0
    hit_tool_round_cap: bool = False
    total_seconds: float = 0.0
    time_to_first_token_seconds: float | None = None
    time_to_first_spoken_seconds: float | None = None
    error: str | None = None


class Done(BaseModel):
    transcript: Transcript


AgentEvent = FillerSpoken | ToolStarted | ToolFinished | AnswerDelta | Done
