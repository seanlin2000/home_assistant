"""The trimmed record of one assistant turn that production keeps for debugging (design doc 10 §3.4).

A Transcript carries everything the agent loop saw, including the full text of every fetched web page. The record keeps what a debugging session
needs (what was asked, what was answered, which tools ran with which arguments and how long they took, token counts and timings, the failure
flags the benchmark gates on) and drops the page text, which is thousands of words per search and can be fetched again. Pure pydantic, so it
imports inside Home Assistant's own Python where the component runs.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from assistant_core.models import GenerationStats, Role, RouteDecision, ToolExchange, Transcript

TURNS_ROUTE = "/turns"


class ToolCallSummary(BaseModel):
    round_index: int
    name: str
    arguments: dict
    seconds: float
    result_chars: int
    error: str | None = None


class TurnRecord(BaseModel):
    recorded_at: str  # ISO 8601, UTC
    source: str  # "home_assistant", "benchmark", "smoke"
    model: str
    user_text: str
    history_turns: int  # messages in the conversation before this turn's question
    final_answer: str
    spoken_chars: int
    route: RouteDecision | None = None
    model_calls: list[GenerationStats] = Field(default_factory=list)
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    tool_call_count: int = 0
    total_seconds: float = 0.0
    time_to_first_token_seconds: float | None = None
    time_to_first_spoken_seconds: float | None = None
    truncated: bool = False
    hit_tool_round_cap: bool = False
    empty_completion_retries: int = 0
    malformed_tool_call_count: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        """True when the turn shows any of the failure signs the benchmark gates on."""
        return bool(self.error) or self.truncated or self.hit_tool_round_cap or self.malformed_tool_call_count > 0 or not self.final_answer.strip()


def summarize_tool_call(exchange: ToolExchange) -> ToolCallSummary:
    return ToolCallSummary(
        round_index=exchange.round_index, name=exchange.call.name, arguments=exchange.call.arguments, seconds=exchange.seconds, result_chars=len(exchange.result), error=exchange.error
    )


def turn_record_from_transcript(transcript: Transcript, source: str = "home_assistant", recorded_at: datetime | None = None) -> TurnRecord:
    user_messages = [message for message in transcript.conversation if message.role == Role.USER]
    return TurnRecord(
        recorded_at=(recorded_at or datetime.now(UTC)).isoformat(timespec="seconds"),
        source=source,
        model=transcript.model,
        user_text=user_messages[-1].content if user_messages else "",
        history_turns=max(len(transcript.conversation) - 1, 0),
        final_answer=transcript.final_answer,
        spoken_chars=len(transcript.spoken_text),
        route=transcript.route,
        model_calls=list(transcript.model_calls),
        tool_calls=[summarize_tool_call(exchange) for exchange in transcript.tool_exchanges],
        tool_call_count=transcript.tool_call_count,
        total_seconds=transcript.total_seconds,
        time_to_first_token_seconds=transcript.time_to_first_token_seconds,
        time_to_first_spoken_seconds=transcript.time_to_first_spoken_seconds,
        truncated=transcript.truncated,
        hit_tool_round_cap=transcript.hit_tool_round_cap,
        empty_completion_retries=transcript.empty_completion_retries,
        malformed_tool_call_count=len(transcript.malformed_tool_calls),
        error=transcript.error,
    )


def turns_url_from_mcp_url(mcp_url: str) -> str:
    """The tool server's record route lives beside its MCP endpoint: http://host:8765/mcp -> http://host:8765/turns."""
    base = mcp_url.rstrip("/")
    if base.endswith("/mcp"):
        base = base[: -len("/mcp")]
    return base + TURNS_ROUTE
