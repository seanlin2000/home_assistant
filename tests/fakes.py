"""Scripted stand-ins for the model and the tool server so the agent loop can be tested deterministically."""

from collections.abc import AsyncIterator

from assistant_core.models import AgentPolicy, Completion, GenerationStats, LLMEvent, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

SEARCH_TOOL = ToolSpec(name="search_and_read", description="search", input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def text_turn(*chunks: str) -> list[LLMEvent]:
    return [
        *(TextDelta(text=chunk) for chunk in chunks),
        Completion(message=Message(role=Role.ASSISTANT, content="".join(chunks)), stats=GenerationStats(model="fake", total_seconds=0.1, time_to_first_token_seconds=0.05)),
    ]


def tool_turn(query: str, call_id: str = "call_0") -> list[LLMEvent]:
    call = ToolCall(id=call_id, name="search_and_read", arguments={"query": query})
    return [ToolCallRequest(call=call), Completion(message=Message(role=Role.ASSISTANT, content="", tool_calls=[call]), stats=GenerationStats(model="fake", total_seconds=0.1))]


class ScriptedLLM:
    def __init__(self, turns: list[list[LLMEvent]]) -> None:
        self._turns = list(turns)
        self.seen_messages: list[list[Message]] = []

    @property
    def model_name(self) -> str:
        return "fake"

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        self.seen_messages.append(list(messages))
        if not self._turns:
            raise AssertionError("model called more times than scripted")
        for event in self._turns.pop(0):
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
