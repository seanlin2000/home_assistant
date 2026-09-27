"""The agent loop: prompt the model, run any tools it asks for, prompt again, stream the spoken answer. Same code in the benchmark and the product."""

import asyncio
import random
import re
import time
from collections.abc import AsyncIterator

from assistant_core.llm_client import LLMClient
from assistant_core.memory import ConversationMemory, NoMemory
from assistant_core.models import (
    SEARCH_TOOL_NAMES,
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
    ToolCallRecord,
    ToolCallRequest,
    ToolFinished,
    ToolStarted,
    Transcript,
)
from assistant_core.prompts import system_prompt

EMPTY_COMPLETION_RETRIES = 1
from assistant_core.router import apply_route, decide_route
from assistant_core.tools import ToolBox

TOOL_LIMIT_NOTICE = "Tool call limit reached. Answer the user now with what you already know; do not call any more tools."
TOOL_UNREACHABLE_NOTICE = "The web search tool is unavailable right now. Tell the user you could not check the web, then answer from your own knowledge with that caveat."
SENTENCE_END = re.compile(r"[.!?][\"')\]]?(\s|$)")


class ModelReply:
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
    transcript = Transcript(model=llm.model_name, system_prompt=system_prompt(), conversation=list(conversation))
    cap = SpokenAnswerCap(policy.word_budget)
    tool_specs = await load_tool_specs(tools, transcript)
    if policy.route_questions and tool_specs:
        transcript.route = await decide_route(llm, conversation, policy)
        messages = apply_route(messages, transcript.route)
    for round_index in range(policy.max_tool_rounds + 1):
        reply = ModelReply()
        async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
            yield event
        if reply_is_empty(reply) and transcript.empty_completion_retries < EMPTY_COMPLETION_RETRIES:
            transcript.empty_completion_retries += 1
            transcript.model_calls.append(reply.completion.stats)
            reply = ModelReply()
            async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
                yield event
        record_model_reply(transcript, reply, messages)
        if not reply.tool_calls:
            break
        if round_index == policy.max_tool_rounds:
            transcript.hit_tool_round_cap = True
            messages.extend(limit_notices(reply.tool_calls))
            reply = ModelReply()
            async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
                yield event
            record_model_reply(transcript, reply, messages)
            break
        async for event in execute_tool_calls(tools, reply.tool_calls, round_index, policy, messages, transcript):
            yield event
    finish_transcript(transcript, reply, cap, messages, started)
    memory.remember(transcript.conversation)
    yield Done(transcript=transcript)


def reply_is_empty(reply: ModelReply) -> bool:  # deslop: allow-comments
    """True when the model produced neither words nor a tool call. Gemma 4 on Ollama does this about one answer in seven: it writes a tool call with
    a small formatting slip, Ollama's parser drops it without reporting anything, and the reply arrives empty. Read aloud, that is silence, so the
    loop asks once more before giving up."""
    return reply.completion is not None and not reply.text_parts and not reply.tool_calls and not reply.malformed


def build_messages(conversation: list[Message], memory: ConversationMemory) -> list[Message]:
    context = memory.get_context(conversation)
    base = system_prompt()
    system_text = base if not context else f"{base}\n\nWhat you remember about this user:\n{context}"
    return [Message(role=Role.SYSTEM, content=system_text), *conversation]


async def load_tool_specs(tools: ToolBox, transcript: Transcript) -> list:
    try:
        return await tools.list_tools()
    except Exception as error:
        transcript.error = f"tool server unavailable: {error}"
        return []


async def stream_model_reply(
    llm: LLMClient, messages: list[Message], tool_specs: list, policy: AgentPolicy, reply: ModelReply, cap: SpokenAnswerCap, transcript: Transcript, started: float
) -> AsyncIterator[AgentEvent]:
    async for event in llm.chat(messages, tool_specs, policy):
        if isinstance(event, TextDelta):
            reply.text_parts.append(event.text)
            spoken = cap.admit(event.text)
            if spoken:
                mark_first_spoken(transcript, started)
                yield AnswerDelta(text=spoken)
        elif isinstance(event, ToolCallRequest):
            if transcript.time_to_first_spoken_seconds is None:  # one filler per exchange, however many tool rounds follow
                mark_first_spoken(transcript, started)
                yield FillerSpoken(text=filler_for(event.call.name, policy))
            reply.tool_calls.append(event.call)
        elif isinstance(event, MalformedToolCall):
            reply.malformed.append(event.raw)
        elif isinstance(event, Completion):
            reply.completion = event


def filler_for(tool_name: str, policy: AgentPolicy) -> str:
    """The sentence spoken while the first tool of an exchange runs: a web line for search tools, a math line for everything else."""
    phrases = policy.filler_phrases if tool_name in SEARCH_TOOL_NAMES else policy.calculate_filler_phrases
    return random.choice(phrases or policy.filler_phrases)


def mark_first_spoken(transcript: Transcript, started: float) -> None:
    if transcript.time_to_first_spoken_seconds is None:
        transcript.time_to_first_spoken_seconds = time.perf_counter() - started


def record_model_reply(transcript: Transcript, reply: ModelReply, messages: list[Message]) -> None:
    transcript.malformed_tool_calls.extend(reply.malformed)
    transcript.tool_call_count += len(reply.tool_calls)
    if reply.completion is None:
        raise RuntimeError("model client ended its stream without a Completion event")
    transcript.model_calls.append(reply.completion.stats)
    if transcript.time_to_first_token_seconds is None:
        transcript.time_to_first_token_seconds = reply.completion.stats.time_to_first_token_seconds
    messages.append(reply.completion.message)


async def execute_tool_calls(tools: ToolBox, calls: list[ToolCall], round_index: int, policy: AgentPolicy, messages: list[Message], transcript: Transcript) -> AsyncIterator[AgentEvent]:
    for call in calls:
        yield ToolStarted(call=call)
        tool_call_record = await execute_one_call(tools, call, round_index, policy)
        transcript.tool_call_records.append(tool_call_record)
        messages.append(Message(role=Role.TOOL, content=tool_call_record.result, tool_call_id=call.id, tool_name=call.name))
        yield ToolFinished(call=call, seconds=tool_call_record.seconds, error=tool_call_record.error)


async def execute_one_call(tools: ToolBox, call: ToolCall, round_index: int, policy: AgentPolicy) -> ToolCallRecord:
    call_started = time.perf_counter()
    try:
        result = await asyncio.wait_for(tools.call(call), timeout=policy.tool_timeout_seconds)
        return ToolCallRecord(round_index=round_index, call=call, result=result, seconds=time.perf_counter() - call_started)
    except Exception as error:
        return ToolCallRecord(round_index=round_index, call=call, result=TOOL_UNREACHABLE_NOTICE, seconds=time.perf_counter() - call_started, error=f"{type(error).__name__}: {error}")


def limit_notices(calls: list[ToolCall]) -> list[Message]:
    return [Message(role=Role.TOOL, content=TOOL_LIMIT_NOTICE, tool_call_id=call.id, tool_name=call.name) for call in calls]


def finish_transcript(transcript: Transcript, reply: ModelReply, cap: SpokenAnswerCap, messages: list[Message], started: float) -> None:
    transcript.final_answer = reply.text.strip()
    transcript.spoken_text = cap.spoken_text
    transcript.truncated = cap.truncated
    transcript.conversation = [message for message in messages if message.role != Role.SYSTEM]
    transcript.total_seconds = time.perf_counter() - started


def total_output_tokens(stats: list[GenerationStats]) -> int:
    return sum(call.output_tokens or 0 for call in stats)
