"""Scripted stand-ins for the model and the tool server so the agent loop can be tested deterministically."""

from collections.abc import AsyncIterator

from assistant_core.models import AgentPolicy, Completion, GenerationStats, LLMEvent, MalformedToolCall, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

SEARCH_TOOL = ToolSpec(name="search_and_read", description="search", input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def text_reply(*chunks: str) -> list[LLMEvent]:
    return [
        *(TextDelta(text=chunk) for chunk in chunks),
        Completion(message=Message(role=Role.ASSISTANT, content="".join(chunks)), stats=GenerationStats(model="fake", total_seconds=0.1, time_to_first_token_seconds=0.05)),
    ]


def tool_reply(query: str, call_id: str = "call_0", tool_name: str = "search_and_read") -> list[LLMEvent]:
    call = ToolCall(id=call_id, name=tool_name, arguments={"query": query})
    return [ToolCallRequest(call=call), Completion(message=Message(role=Role.ASSISTANT, content="", tool_calls=[call]), stats=GenerationStats(model="fake", total_seconds=0.1))]


def several_tool_calls_reply(*queries: str) -> list[LLMEvent]:
    """One model turn asking for a search per query at once."""
    calls = [ToolCall(id=f"call_{index}", name="search_and_read", arguments={"query": query}) for index, query in enumerate(queries)]
    return [*(ToolCallRequest(call=call) for call in calls), Completion(message=Message(role=Role.ASSISTANT, content="", tool_calls=calls), stats=GenerationStats(model="fake", total_seconds=0.1))]


def malformed_reply(raw: str = '{"query": "fed funds') -> list[LLMEvent]:
    """A turn whose only output is a tool call the client could not parse."""
    return [MalformedToolCall(raw=raw), Completion(message=Message(role=Role.ASSISTANT, content=raw), stats=GenerationStats(model="fake", total_seconds=0.1))]


def tool_replies_past_the_cap(policy: AgentPolicy) -> list[list[LLMEvent]]:
    """One tool request per allowed round plus the one that trips the round cap."""
    return [tool_reply(f"q{round_index}", f"call_{round_index}") for round_index in range(policy.max_tool_rounds + 1)]


def empty_reply() -> list[LLMEvent]:
    """What Ollama hands back when it swallowed the model's output: a completion with no text and no tool calls."""
    return [Completion(message=Message(role=Role.ASSISTANT, content=""), stats=GenerationStats(model="fake", total_seconds=0.1))]


class ScriptedLLM:
    def __init__(self, replies: list[list[LLMEvent]]) -> None:
        self._replies = list(replies)
        self.seen_messages: list[list[Message]] = []

    @property
    def model_name(self) -> str:
        return "fake"

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        self.seen_messages.append(list(messages))
        if not self._replies:
            raise AssertionError("model called more times than scripted")
        for event in self._replies.pop(0):
            yield event


class FakeToolBox:
    def __init__(self, result: str = "[1] Source\nURL: http://x\nThe rate is 4.25 percent.", fail: bool = False) -> None:
        self._result = result
        self._fail = fail
        self.calls: list[ToolCall] = []

    async def list_tools(self) -> list[ToolSpec]:
        return [SEARCH_TOOL]

    async def call(self, call: ToolCall) -> str:
        self.calls.append(call)
        if self._fail:
            raise ConnectionError("server down")
        return self._result
