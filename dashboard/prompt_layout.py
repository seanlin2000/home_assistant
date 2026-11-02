"""Rebuild the prompt each model call of an exchange sent, measure its parts in tokens, and say where the prompt cache stopped (design doc v2/13
section 3.10).

llama-server renders the messages through the model's own chat template and counts the tokens, so the sizes are the ones the model read. A part
ends where a render of the prompt up to that part stops matching the whole prompt. Such a render closes with the template's next marker (the
opener of a turn, say), and when the whole prompt carries the same marker it is counted with the part before; a boundary can sit a token late.
"""

import asyncio
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

from assistant_core.exchange_record import ExchangeTrace
from assistant_core.models import GenerationStats, Message, Role, ToolSpec
from assistant_core.prompts import question_with_block

BOUNDARY_SLACK_TOKENS = 2  # a part's end can be a token late (above), and the cache can stop a token short of it
EXACT_SLACK_TOKENS = 2
CLOSING_LABEL = "closing markers"  # what the template adds after the last part, such as the opener of the model's turn


class PromptCounter(Protocol):
    async def render_prompt(self, messages: list[Message], tools: list[ToolSpec]) -> str: ...

    async def count_tokens(self, text: str) -> int: ...


class SegmentKind(StrEnum):
    SYSTEM = "system"
    TOOLS = "tools"
    EARLIER = "earlier"
    BLOCK = "block"
    QUESTION = "question"
    TOOL_ROUND = "tool_round"
    REST = "rest"


class Segment(BaseModel):
    kind: SegmentKind
    label: str
    start: int
    tokens: int

    @property
    def end(self) -> int:
        return self.start + self.tokens


class Verdict(StrEnum):
    EXPECTED = "expected"
    EARLY = "early"
    FULL_REREAD = "full_reread"
    UNKNOWN = "unknown"


class CallLayout(BaseModel):
    number: int  # as the timing chart numbers it
    prompt_tokens: int
    cached_tokens: int | None
    segments: list[Segment]
    verdict: Verdict
    explanation: str


class ToolSize(BaseModel):
    name: str
    tokens: int


class PromptLayout(BaseModel):
    exact: bool
    note: str = ""
    system_prompt: str
    per_question_block: str
    tools: list[ToolSize]
    calls: list[CallLayout]


class ReplyPrompt(BaseModel):
    """The prompt one kept reply was written from: its size, rebuilt, and how many tool rounds it held."""

    tokens: int
    rounds_held: int


class PromptParts(BaseModel):
    """The messages of the exchange in the order the harness lays the prompt out (design doc v2/02 section 3.3)."""

    system: Message
    earlier: list[Message]
    spoken: Message  # the question as asked
    per_question_block: str
    after: list[Message]  # the model's replies and the tool results, in order
    reply_starts: list[int]  # where each kept reply begins in `after`, which is also how much of `after` the prompt that wrote it held

    def question(self) -> Message:
        """As the model read it, with the block in front."""
        if not self.per_question_block:
            return self.spoken
        return self.spoken.model_copy(update={"content": question_with_block(self.spoken.content, self.per_question_block)})

    def prompt_before(self, reply_start: int) -> list[Message]:
        return [self.system, *self.earlier, self.question(), *self.after[:reply_start]]

    def last_prompt(self) -> list[Message]:
        return self.prompt_before(self.reply_starts[-1] if self.reply_starts else 0)

    def rounds(self) -> list[tuple[int, str]]:
        """Each tool round the last prompt holds: where it ends in `after`, and the tools it called."""
        return [(end, ", ".join(call.name for call in self.after[start].tool_calls)) for start, end in zip(self.reply_starts, self.reply_starts[1:]) if self.after[start].tool_calls]

    def rounds_before(self, reply_start: int) -> int:
        return sum(1 for end, _names in self.rounds() if end <= reply_start)


async def prompt_layout(trace: ExchangeTrace, model_calls: list[GenerationStats], counter: PromptCounter) -> PromptLayout:
    parts = prompt_parts(trace)
    tools = trace.tool_specs
    segments = await measured_segments(parts, tools, counter)
    reply_prompt_tokens = list(await asyncio.gather(*(count_rendered(parts.prompt_before(start), tools, counter) for start in parts.reply_starts)))
    unrecorded = unrecorded_tokens(tools, model_calls, reply_prompt_tokens)
    if unrecorded:
        segments = with_unrecorded_segment(segments, unrecorded)
        reply_prompt_tokens = [tokens + unrecorded for tokens in reply_prompt_tokens]
    replies = [ReplyPrompt(tokens=tokens, rounds_held=parts.rounds_before(start)) for tokens, start in zip(reply_prompt_tokens, parts.reply_starts)]
    exact = not unrecorded and all(call_matches(stats, reply.tokens) for stats, reply in zip(model_calls, matched_replies(model_calls, replies)))
    first_call_expects = None if unrecorded else stable_end(segments)
    return PromptLayout(
        exact=exact,
        note=layout_note(tools, exact),
        system_prompt=parts.system.content,
        per_question_block=parts.per_question_block,
        tools=await tool_sizes(parts.system, tools, counter),
        calls=call_layouts(model_calls, segments, replies, first_call_expects),
    )


def prompt_parts(trace: ExchangeTrace) -> PromptParts:
    conversation = trace.transcript.conversation
    question_index = max((index for index, message in enumerate(conversation) if message.role == Role.USER), default=0)
    after = conversation[question_index + 1 :]
    return PromptParts(
        system=Message(role=Role.SYSTEM, content=trace.transcript.system_prompt),
        earlier=conversation[:question_index],
        spoken=conversation[question_index],
        per_question_block=trace.transcript.per_question_block,
        after=after,
        reply_starts=[index for index, message in enumerate(after) if message.role == Role.ASSISTANT],
    )


async def measured_segments(parts: PromptParts, tools: list[ToolSpec], counter: PromptCounter) -> list[Segment]:
    """Each part's end in characters, from where a render up to it stops matching the whole prompt, then in tokens, by counting the text before it."""
    whole = await counter.render_prompt(parts.last_prompt(), tools)
    beginnings = part_beginnings(parts, tools)
    ends = await asyncio.gather(*(matching_length(messages, part_tools, whole, counter) for _kind, _label, messages, part_tools in beginnings))
    token_ends = await asyncio.gather(*(counter.count_tokens(whole[:end]) for end in ends))
    total = await counter.count_tokens(whole)
    labels = [(kind, label) for kind, label, _messages, _tools in beginnings] + [(SegmentKind.REST, CLOSING_LABEL)]
    starts = [0, *token_ends]
    stops = [*token_ends, total]
    return [Segment(kind=kind, label=label, start=start, tokens=stop - start) for (kind, label), start, stop in zip(labels, starts, stops) if stop > start]


def part_beginnings(parts: PromptParts, tools: list[ToolSpec]) -> list[tuple[SegmentKind, str, list[Message], list[ToolSpec]]]:
    """The messages up to the end of each part. The block ends where the question's own words begin, so it is the question with no words."""
    system = [parts.system]
    beginnings = [(SegmentKind.SYSTEM, "system rules", system, [])]
    if tools:
        beginnings.append((SegmentKind.TOOLS, "tool definitions", system, tools))
    beginnings.append((SegmentKind.EARLIER, "earlier exchanges", [*system, *parts.earlier], tools))
    if parts.per_question_block:
        wordless = parts.spoken.model_copy(update={"content": question_with_block("", parts.per_question_block)})
        beginnings.append((SegmentKind.BLOCK, "per-question block", [*system, *parts.earlier, wordless], tools))
    beginnings.append((SegmentKind.QUESTION, "question", parts.prompt_before(0), tools))
    for number, (round_end, names) in enumerate(parts.rounds(), start=1):
        beginnings.append((SegmentKind.TOOL_ROUND, f"tool round {number} ({names})", parts.prompt_before(round_end), tools))
    return beginnings


async def matching_length(messages: list[Message], tools: list[ToolSpec], whole: str, counter: PromptCounter) -> int:
    rendered = await counter.render_prompt(messages, tools)
    return common_prefix_length(rendered, whole)


def common_prefix_length(first: str, second: str) -> int:
    length = 0
    for first_character, second_character in zip(first, second):
        if first_character != second_character:
            break
        length += 1
    return length


async def count_rendered(messages: list[Message], tools: list[ToolSpec], counter: PromptCounter) -> int:
    return await counter.count_tokens(await counter.render_prompt(messages, tools))


def unrecorded_tokens(tools: list[ToolSpec], model_calls: list[GenerationStats], reply_prompt_tokens: list[int]) -> int:
    """A trace written before traces kept the tool definitions and the block is rebuilt without them; the first call's recorded size says how much is missing."""
    first_recorded = next((stats.prompt_tokens for stats in model_calls if stats.prompt_tokens is not None), None)
    if tools or first_recorded is None or not reply_prompt_tokens:
        return 0
    return max(first_recorded - reply_prompt_tokens[0], 0)


def with_unrecorded_segment(segments: list[Segment], unrecorded: int) -> list[Segment]:
    """Placed after the system rules, where the tool definitions, most of what is missing, sit."""
    shifted = [segment.model_copy(update={"start": segment.start + unrecorded}) if segment.kind != SegmentKind.SYSTEM else segment for segment in segments]
    system_end = next((segment.end for segment in segments if segment.kind == SegmentKind.SYSTEM), 0)
    missing = Segment(kind=SegmentKind.TOOLS, label="tool definitions and per-question block (not recorded)", start=system_end, tokens=unrecorded)
    return sorted([*shifted, missing], key=lambda segment: segment.start)


def matched_replies(model_calls: list[GenerationStats], replies: list[ReplyPrompt]) -> list[ReplyPrompt]:
    """The rebuilt prompt each call sent: the one nearest its recorded size, since a retried call sends its round's prompt twice; in order when no size was recorded."""
    if not replies:
        return [ReplyPrompt(tokens=0, rounds_held=0) for _stats in model_calls]
    return [nearest(stats.prompt_tokens, replies) if stats.prompt_tokens is not None else replies[min(index, len(replies) - 1)] for index, stats in enumerate(model_calls)]


def nearest(target: int, replies: list[ReplyPrompt]) -> ReplyPrompt:
    return min(replies, key=lambda reply: abs(reply.tokens - target))


def call_matches(stats: GenerationStats, rebuilt_tokens: int) -> bool:
    return stats.prompt_tokens is not None and abs(stats.prompt_tokens - rebuilt_tokens) <= EXACT_SLACK_TOKENS


def call_layouts(model_calls: list[GenerationStats], segments: list[Segment], replies: list[ReplyPrompt], first_call_expects: int | None) -> list[CallLayout]:
    """The first call should find the system rules and tool definitions cached (unknown when their size was not recorded); each later call, everything
    the call before it sent."""
    layouts = []
    expected_cached = first_call_expects
    for index, (stats, reply) in enumerate(zip(model_calls, matched_replies(model_calls, replies))):
        prompt_tokens = stats.prompt_tokens if stats.prompt_tokens is not None else reply.tokens
        call_segments = segments_within(held_segments(segments, reply.rounds_held), prompt_tokens)
        verdict, explanation = cache_verdict(stats.cached_prompt_tokens, call_segments, expected_cached)
        layouts.append(CallLayout(number=index + 1, prompt_tokens=prompt_tokens, cached_tokens=stats.cached_prompt_tokens, segments=call_segments, verdict=verdict, explanation=explanation))
        expected_cached = prompt_tokens
    return layouts


def held_segments(segments: list[Segment], rounds_held: int) -> list[Segment]:
    """The parts of the last call's prompt that an earlier call's prompt held: everything through the question, and the tool rounds before its reply."""
    rounds = [segment for segment in segments if segment.kind == SegmentKind.TOOL_ROUND]
    kept_rounds = rounds[:rounds_held]
    return [segment for segment in segments if segment.kind not in (SegmentKind.TOOL_ROUND, SegmentKind.REST) or segment in kept_rounds]


def segments_within(segments: list[Segment], prompt_tokens: int) -> list[Segment]:
    """The parts cut where the call's own prompt ended, with what its template added after them."""
    kept = [segment.model_copy(update={"tokens": min(segment.end, prompt_tokens) - segment.start}) for segment in segments if segment.start < prompt_tokens]
    kept_end = kept[-1].end if kept else 0
    if prompt_tokens > kept_end:
        kept.append(Segment(kind=SegmentKind.REST, label=CLOSING_LABEL, start=kept_end, tokens=prompt_tokens - kept_end))
    return kept


def cache_verdict(cached_tokens: int | None, segments: list[Segment], expected_cached: int | None) -> tuple[Verdict, str]:
    if cached_tokens is None:
        return Verdict.UNKNOWN, "the model server did not say how much came from the cache"
    if cached_tokens == 0:
        return Verdict.FULL_REREAD, "full re-read: nothing came from the cache"
    reach = cache_reach(cached_tokens, segments)
    if expected_cached is None:
        return Verdict.UNKNOWN, reach
    if cached_tokens + BOUNDARY_SLACK_TOKENS >= expected_cached:
        return Verdict.EXPECTED, reach
    return Verdict.EARLY, f"{reach}, though the first {expected_cached:,} tokens were expected from the cache"


def stable_end(segments: list[Segment]) -> int:
    stable = [segment.end for segment in segments if segment.kind in (SegmentKind.SYSTEM, SegmentKind.TOOLS)]
    return max(stable, default=0)


def cache_reach(cached_tokens: int, segments: list[Segment]) -> str:
    """Where the cached beginning ended, in the words of the parts: at a part's edge, or partway into one."""
    first_fresh = next((segment for segment in segments if segment.end > cached_tokens + BOUNDARY_SLACK_TOKENS), None)
    if first_fresh is None:
        return "came entirely from the cache"
    held = [segment for segment in segments if segment.end <= cached_tokens + BOUNDARY_SLACK_TOKENS]
    if cached_tokens - first_fresh.start <= BOUNDARY_SLACK_TOKENS:
        return f"cache held through {held[-1].label}, read from {first_fresh.label}" if held else f"read from {first_fresh.label}"
    return f"cache held {cached_tokens - first_fresh.start:,} of the {first_fresh.tokens:,} tokens of {first_fresh.label}, read the rest"


async def tool_sizes(system: Message, tools: list[ToolSpec], counter: PromptCounter) -> list[ToolSize]:
    """Each tool's definition alone, against the system rules with no tools."""
    if not tools:
        return []
    without_tools, *with_each = await asyncio.gather(count_rendered([system], [], counter), *(count_rendered([system], [tool], counter) for tool in tools))
    return [ToolSize(name=tool.name, tokens=tokens - without_tools) for tool, tokens in zip(tools, with_each)]


def layout_note(tools: list[ToolSpec], exact: bool) -> str:
    if not tools:
        return "Recorded before traces kept the tool definitions and the per-question block, so their size is inferred from the first call's prompt."
    return "" if exact else "The rebuilt prompt does not match the size the model server recorded, so the parts are approximate (the template or a tool may have changed since)."
