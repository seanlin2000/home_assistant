"""The agent loop: prompt the model, run any tools it asks for, prompt again, stream the spoken answer. Same code in the benchmark and the product."""

import asyncio
import json
import random
import re
import time
from collections.abc import AsyncIterator
from datetime import date

from assistant_core.llm_client import LLMClient
from assistant_core.memory import ConversationMemory, NoMemory
from assistant_core.models import (
    SEARCH_TOOL_NAMES,
    WEATHER_TOOL_NAMES,
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
from assistant_core.prompts import SILENCE_MARKER, per_question_block, question_with_block, system_prompt
from assistant_core.router import decide_route, directive_for, route_to_offered_tools, tool_round_cap
from assistant_core.tool_guards import GuardedToolBox, ToolRefused, load_tool_table
from assistant_core.tools import ToolBox

EMPTY_COMPLETION_RETRIES = 1
MALFORMED_RETRIES = 1
REPEATED_CALL_NOTE = "You already made this exact call for this question; here is its result again. Use it rather than calling again."
TOOL_LIMIT_NOTICE = "Tool call limit reached. Answer the user now with what you already know; do not call any more tools."
TOOL_UNREACHABLE_NOTICE = "The web search tool is unavailable right now. Tell the user you could not check the web, then answer from your own knowledge with that caveat."
SENTENCE_END = re.compile(r"[.!?][\"')\]]?(\s|$)")
# Gemma 4 now and then writes its tool call as text ("<tool_call> search_and_read(query=...)", "<execute_tool> ...") instead of calling the tool.
MARKUP_START = "<"
WRITTEN_TOOL_CALL = re.compile(r"^\s*<\|?\s*(tool_call|execute_tool|tool_code|function_call)\b", re.IGNORECASE)


class SpeechHold:
    """Holds back the start of a model reply while it could still be the silence marker, so a reply that is only the marker is never spoken.
    The moment the text stops matching the marker, everything held is released at once, so an ordinary answer is spoken without delay. A reply
    that starts with markup is held to its end, since no spoken answer starts with "<"; it may be a tool call written as text."""

    def __init__(self) -> None:
        self._held_parts: list[str] = []
        self._released = False

    def release(self, text: str) -> str:
        """The text that may be spoken now: nothing while the reply so far could still be the marker or is markup, then everything held plus this chunk."""
        if self._released:
            return text
        self._held_parts.append(text)
        held_text = "".join(self._held_parts)
        if SILENCE_MARKER.startswith(held_text.strip()) or held_text.lstrip().startswith(MARKUP_START):
            return ""
        self._released = True
        return held_text

    def leftover(self) -> str:
        """At the end of the reply: held text that is neither the silence marker nor a written tool call, which may now be spoken."""
        held_text = "".join(self._held_parts)
        if self._released or held_text.strip() == SILENCE_MARKER or WRITTEN_TOOL_CALL.match(held_text):
            return ""
        return held_text


class ModelReply:
    """What one call to the model produced, collected while its events are streamed onward."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_calls: list[ToolCall] = []
        self.malformed: list[str] = []
        self.completion: Completion | None = None
        self.speech_hold = SpeechHold()

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    @property
    def is_silence(self) -> bool:
        return self.text.strip() == SILENCE_MARKER


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
    tools = GuardedToolBox(tools, load_tool_table(), conversation)
    messages = [Message(role=Role.SYSTEM, content=system_prompt()), *conversation]
    transcript = Transcript(model=llm.model_name, system_prompt=system_prompt(), conversation=list(conversation))
    cap = SpokenAnswerCap(policy.word_budget)
    tool_specs = await load_tool_specs(tools, transcript)
    directive = None
    if policy.route_questions and tool_specs:
        transcript.route = route_to_offered_tools(await decide_route(llm, conversation, policy), tool_specs)
        directive = directive_for(transcript.route)
    spoken_question = put_block_before_question(messages, per_question_block(date.today(), directive, memory.get_context(conversation)))
    max_tool_rounds = tool_round_cap(transcript.route, policy.max_tool_rounds)
    runner = ToolCallRunner(tools, policy)
    for round_index in range(max_tool_rounds + 1):
        reply = ModelReply()
        async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
            yield event
        if may_ask_again(reply, transcript):
            set_aside_unusable_reply(reply, transcript)
            reply = ModelReply()
            async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
                yield event
        record_model_reply(transcript, reply, messages)
        if not reply.tool_calls:
            break
        if round_index == max_tool_rounds:
            transcript.hit_tool_round_cap = True
            messages.extend(limit_notices(reply.tool_calls))
            reply = ModelReply()
            async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
                yield event
            record_model_reply(transcript, reply, messages)
            break
        async for event in execute_tool_calls(runner, reply.tool_calls, round_index, messages, transcript):
            yield event
    restore_spoken_question(messages, spoken_question)
    finish_transcript(transcript, reply, cap, messages, started)
    transcript.untrusted = tools.untrusted
    memory.remember(transcript.conversation)
    yield Done(transcript=transcript)


def reply_is_empty(reply: ModelReply) -> bool:  # deslop: allow-comments
    """True when the model produced neither words nor a tool call. Gemma 4 on Ollama does this about one answer in seven: it writes a tool call with
    a small formatting slip, Ollama's parser drops it without reporting anything, and the reply arrives empty. Read aloud, that is silence, so the
    loop asks once more before giving up."""
    return reply.completion is not None and not reply.text_parts and not reply.tool_calls and not reply.malformed


def reply_is_broken(reply: ModelReply) -> bool:
    """The only output was an unparseable or written-out tool call, which left in the history would teach the model the broken format (design doc v2/04 section 3.3)."""
    if reply.completion is None or reply.tool_calls:
        return False
    return (bool(reply.malformed) and not reply.text_parts) or bool(WRITTEN_TOOL_CALL.match(reply.text))


def may_ask_again(reply: ModelReply, transcript: Transcript) -> bool:
    if reply_is_empty(reply):
        return transcript.empty_completion_retries < EMPTY_COMPLETION_RETRIES
    return reply_is_broken(reply) and transcript.malformed_retries < MALFORMED_RETRIES


def set_aside_unusable_reply(reply: ModelReply, transcript: Transcript) -> None:
    """Count the reply and keep its cost and any broken call on the transcript, but leave it out of the messages the model sees next."""
    if reply_is_empty(reply):
        transcript.empty_completion_retries += 1
    else:
        transcript.malformed_retries += 1
        transcript.malformed_tool_calls.extend(reply.malformed or [reply.text])
    transcript.model_calls.append(reply.completion.stats)


def put_block_before_question(messages: list[Message], block: str) -> tuple[int, Message] | None:
    """Prefix the latest user message with the per-question block and return where it was and what was said, so the history keeps the words as spoken.
    Earlier questions are replayed without their blocks, so the prompt departs from the cached one only at the previous question (design doc v2/02 3.3)."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == Role.USER:
            spoken = messages[index]
            messages[index] = spoken.model_copy(update={"content": question_with_block(spoken.content, block)})
            return index, spoken
    return None


def restore_spoken_question(messages: list[Message], spoken_question: tuple[int, Message] | None) -> None:
    if spoken_question is not None:
        index, spoken = spoken_question
        messages[index] = spoken


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
            speakable = reply.speech_hold.release(event.text)
            spoken = cap.admit(speakable) if speakable else ""
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
    leftover = reply.speech_hold.leftover()
    spoken = cap.admit(leftover) if leftover else ""
    if spoken:
        mark_first_spoken(transcript, started)
        yield AnswerDelta(text=spoken)


def filler_for(tool_name: str, policy: AgentPolicy) -> str:
    """The sentence spoken while the first tool of an exchange runs: a web line for search tools, a forecast line for the weather, a math line for everything else."""
    if tool_name in SEARCH_TOOL_NAMES:
        phrases = policy.filler_phrases
    elif tool_name in WEATHER_TOOL_NAMES:
        phrases = policy.weather_filler_phrases
    else:
        phrases = policy.calculate_filler_phrases
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


async def execute_tool_calls(runner: "ToolCallRunner", calls: list[ToolCall], round_index: int, messages: list[Message], transcript: Transcript) -> AsyncIterator[AgentEvent]:
    for call in calls:
        yield ToolStarted(call=call)
    for tool_call_record in await runner.run_turn(calls, round_index):
        transcript.tool_call_records.append(tool_call_record)
        messages.append(Message(role=Role.TOOL, content=tool_call_record.result, tool_call_id=tool_call_record.call.id, tool_name=tool_call_record.call.name))
        yield ToolFinished(call=tool_call_record.call, seconds=tool_call_record.seconds, error=tool_call_record.error)


class ToolCallRunner:
    """Runs the calls of one model turn at the same time, and answers a call already made for this question from its first result instead of the network."""

    def __init__(self, tools: ToolBox, policy: AgentPolicy) -> None:
        self._tools = tools
        self._policy = policy
        self._first_results: dict[str, ToolCallRecord] = {}

    async def run_turn(self, calls: list[ToolCall], round_index: int) -> list[ToolCallRecord]:
        """One record per call, in the order the model asked."""
        records = await asyncio.gather(*(execute_one_call(self._tools, call, round_index, self._policy) for call in self._calls_not_yet_made(calls)))
        ran_now = {record.call.id: record for record in records}
        self._first_results.update({call_key(record.call): record for record in records})
        return [ran_now.get(call.id) or repeat_of(self._first_results[call_key(call)], call, round_index) for call in calls]

    def _calls_not_yet_made(self, calls: list[ToolCall]) -> list[ToolCall]:
        """The first of each distinct call in this turn that no earlier turn of the question made, in the order the model asked."""
        first_of_each: dict[str, ToolCall] = {}
        for call in calls:
            first_of_each.setdefault(call_key(call), call)
        return [call for key, call in first_of_each.items() if key not in self._first_results]


def call_key(call: ToolCall) -> str:
    return f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"


def repeat_of(first: ToolCallRecord, call: ToolCall, round_index: int) -> ToolCallRecord:
    return ToolCallRecord(round_index=round_index, call=call, result=f"{REPEATED_CALL_NOTE}\n{first.result}", seconds=0.0, refused=first.refused, repeated=True)


async def execute_one_call(tools: ToolBox, call: ToolCall, round_index: int, policy: AgentPolicy) -> ToolCallRecord:
    call_started = time.perf_counter()
    try:
        result = await asyncio.wait_for(tools.call(call), timeout=policy.tool_timeout_seconds)
        return ToolCallRecord(round_index=round_index, call=call, result=result, seconds=time.perf_counter() - call_started)
    except ToolRefused as refusal:
        return ToolCallRecord(round_index=round_index, call=call, result=str(refusal), seconds=time.perf_counter() - call_started, refused=True)
    except Exception as error:
        return ToolCallRecord(round_index=round_index, call=call, result=TOOL_UNREACHABLE_NOTICE, seconds=time.perf_counter() - call_started, error=f"{type(error).__name__}: {error}")


def limit_notices(calls: list[ToolCall]) -> list[Message]:
    return [Message(role=Role.TOOL, content=TOOL_LIMIT_NOTICE, tool_call_id=call.id, tool_name=call.name) for call in calls]


def finish_transcript(transcript: Transcript, reply: ModelReply, cap: SpokenAnswerCap, messages: list[Message], started: float) -> None:
    transcript.final_answer = reply.text.strip()
    transcript.stayed_silent = reply.is_silence
    transcript.spoken_text = cap.spoken_text
    transcript.truncated = cap.truncated
    transcript.conversation = [message for message in messages if message.role != Role.SYSTEM]
    transcript.total_seconds = time.perf_counter() - started


def total_output_tokens(stats: list[GenerationStats]) -> int:
    return sum(call.output_tokens or 0 for call in stats)
