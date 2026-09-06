"""The agent loop: prompt the model, run any tools it asks for, prompt again, stream the spoken answer. Same code in the benchmark and the product."""

import asyncio
import random
import re
import time
from collections.abc import AsyncIterator

from assistant_core.llm_client import LLMClient
from assistant_core.memory import ConversationMemory, NoMemory
from assistant_core.models import (
    AgentEvent,
    AgentPolicy,
    AnswerDelta,
    Completion,
    Done,
    FillerSpoken,
    GenerationStats,
    MalformedToolCall,
    Message,
    Role,
    TextDelta,
    ToolCall,
    ToolCallRequest,
    ToolExchange,
    ToolFinished,
    ToolStarted,
    Transcript,
)
from assistant_core.prompts import SYSTEM_PROMPT
from assistant_core.tools import ToolBox

TOOL_LIMIT_NOTICE = "Tool call limit reached. Answer the user now with what you already know; do not call any more tools."
TOOL_UNREACHABLE_NOTICE = "The web search tool is unavailable right now. Tell the user you could not check the web, then answer from your own knowledge with that caveat."
SENTENCE_END = re.compile(r"[.!?][\"')\]]?(\s|$)")


class ModelTurn:
    """What one call to the model produced, collected while its events are streamed onward."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_calls: list[ToolCall] = []
        self.malformed: list[str] = []
        self.completion: Completion | None = None

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


class SpokenAnswerCap:
    """Soft word cap: past the budget, speech stops at the end of the current sentence."""

    def __init__(self, word_budget: int) -> None:
        self._word_budget = word_budget
        self._words_spoken = 0
        self._closed = False
        self.truncated = False
        self.spoken_parts: list[str] = []

    def admit(self, text: str) -> str:
        if self._closed:
            self.truncated = True
            return ""
        self._words_spoken += len(text.split())
        if self._words_spoken > self._word_budget and SENTENCE_END.search(text):
            self._closed = True
        self.spoken_parts.append(text)
        return text

    @property
    def spoken_text(self) -> str:
        return "".join(self.spoken_parts).strip()


async def run(conversation: list[Message], llm: LLMClient, tools: ToolBox, policy: AgentPolicy, memory: ConversationMemory | None = None) -> AsyncIterator[AgentEvent]:
    started = time.perf_counter()
    memory = memory or NoMemory()
    messages = build_messages(conversation, memory)
    transcript = Transcript(model=llm.model_name, system_prompt=SYSTEM_PROMPT, conversation=list(conversation))
    cap = SpokenAnswerCap(policy.word_budget)
    tool_specs = await load_tool_specs(tools, transcript)
    for round_index in range(policy.max_tool_rounds + 1):
        turn = ModelTurn()
        async for event in stream_model_turn(llm, messages, tool_specs, policy, turn, cap, transcript, started):
            yield event
        record_turn(transcript, turn, messages)
        if not turn.tool_calls:
            break
        if round_index == policy.max_tool_rounds:
            transcript.hit_tool_round_cap = True
            messages.extend(limit_notices(turn.tool_calls))
            turn = await answer_without_tools(llm, messages, tool_specs, policy, transcript, cap)
            break
        async for event in execute_tool_calls(tools, turn.tool_calls, round_index, policy, messages, transcript):
            yield event
    finish_transcript(transcript, turn, cap, messages, started)
    memory.remember(transcript.conversation)
    yield Done(transcript=transcript)


def build_messages(conversation: list[Message], memory: ConversationMemory) -> list[Message]:
    context = memory.get_context(conversation)
    system_text = SYSTEM_PROMPT if not context else f"{SYSTEM_PROMPT}\n\nWhat you remember about this user:\n{context}"
    return [Message(role=Role.SYSTEM, content=system_text), *conversation]


async def load_tool_specs(tools: ToolBox, transcript: Transcript) -> list:
    try:
        return await tools.list_tools()
    except Exception as error:
        transcript.error = f"tool server unavailable: {error}"
        return []


async def stream_model_turn(
    llm: LLMClient, messages: list[Message], tool_specs: list, policy: AgentPolicy, turn: ModelTurn, cap: SpokenAnswerCap, transcript: Transcript, started: float
) -> AsyncIterator[AgentEvent]:
    async for event in llm.chat(messages, tool_specs, policy):
        if isinstance(event, TextDelta):
            turn.text_parts.append(event.text)
            spoken = cap.admit(event.text)
            if spoken:
                mark_first_spoken(transcript, started)
                yield AnswerDelta(text=spoken)
        elif isinstance(event, ToolCallRequest):
            if not turn.tool_calls:
                mark_first_spoken(transcript, started)
                yield FillerSpoken(text=random.choice(policy.filler_phrases))
            turn.tool_calls.append(event.call)
        elif isinstance(event, MalformedToolCall):
            turn.malformed.append(event.raw)
        elif isinstance(event, Completion):
            turn.completion = event


def mark_first_spoken(transcript: Transcript, started: float) -> None:
    if transcript.time_to_first_spoken_seconds is None:
        transcript.time_to_first_spoken_seconds = time.perf_counter() - started


def record_turn(transcript: Transcript, turn: ModelTurn, messages: list[Message]) -> None:
    transcript.malformed_tool_calls.extend(turn.malformed)
    transcript.tool_call_count += len(turn.tool_calls)
    if turn.completion is None:
        raise RuntimeError("model client ended its stream without a Completion event")
    transcript.model_calls.append(turn.completion.stats)
    if transcript.time_to_first_token_seconds is None:
        transcript.time_to_first_token_seconds = turn.completion.stats.time_to_first_token_seconds
    messages.append(turn.completion.message)


async def execute_tool_calls(tools: ToolBox, calls: list[ToolCall], round_index: int, policy: AgentPolicy, messages: list[Message], transcript: Transcript) -> AsyncIterator[AgentEvent]:
    for call in calls:
        yield ToolStarted(call=call)
        exchange = await execute_one_call(tools, call, round_index, policy)
        transcript.tool_exchanges.append(exchange)
        messages.append(Message(role=Role.TOOL, content=exchange.result, tool_call_id=call.id, tool_name=call.name))
        yield ToolFinished(call=call, seconds=exchange.seconds, error=exchange.error)


async def execute_one_call(tools: ToolBox, call: ToolCall, round_index: int, policy: AgentPolicy) -> ToolExchange:
    call_started = time.perf_counter()
    try:
        result = await asyncio.wait_for(tools.call(call), timeout=policy.tool_timeout_seconds)
        return ToolExchange(round_index=round_index, call=call, result=result, seconds=time.perf_counter() - call_started)
    except Exception as error:
        return ToolExchange(round_index=round_index, call=call, result=TOOL_UNREACHABLE_NOTICE, seconds=time.perf_counter() - call_started, error=f"{type(error).__name__}: {error}")


def limit_notices(calls: list[ToolCall]) -> list[Message]:
    return [Message(role=Role.TOOL, content=TOOL_LIMIT_NOTICE, tool_call_id=call.id, tool_name=call.name) for call in calls]


async def answer_without_tools(llm: LLMClient, messages: list[Message], tool_specs: list, policy: AgentPolicy, transcript: Transcript, cap: SpokenAnswerCap) -> ModelTurn:
    turn = ModelTurn()
    async for event in llm.chat(messages, tool_specs, policy):
        if isinstance(event, TextDelta):
            turn.text_parts.append(event.text)
            cap.admit(event.text)
        elif isinstance(event, ToolCallRequest):
            turn.tool_calls.append(event.call)
        elif isinstance(event, Completion):
            turn.completion = event
    record_turn(transcript, turn, messages)
    return turn


def finish_transcript(transcript: Transcript, turn: ModelTurn, cap: SpokenAnswerCap, messages: list[Message], started: float) -> None:
    transcript.final_answer = turn.text.strip()
    transcript.spoken_text = cap.spoken_text
    transcript.truncated = cap.truncated
    transcript.conversation = [message for message in messages if message.role != Role.SYSTEM]
    transcript.total_seconds = time.perf_counter() - started


def total_output_tokens(stats: list[GenerationStats]) -> int:
    return sum(call.output_tokens or 0 for call in stats)
