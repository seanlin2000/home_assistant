"""Pure translation between Home Assistant's chat log vocabulary and assistant_core's, kept free of Home Assistant imports so it is unit-testable in the project venv.

Home Assistant hands the agent a chat log of typed content objects and expects a stream of delta dictionaries back. assistant_core speaks Message
objects in and AgentEvent objects out. Everything the entity does is these two conversions, the answer it gives when the harness is down, and the
decision whether to listen for a follow-up.
"""

import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from assistant_core.models import AgentEvent, AnswerDelta, Done, FillerSpoken, Message, Role, Transcript
from assistant_core.prompts import ACKNOWLEDGEMENT_REPLY

_LOGGER = logging.getLogger(__name__)

EMPTY_ANSWER_FALLBACK = "Sorry, I could not come up with an answer to that."
HARNESS_UNREACHABLE_ANSWER = "I can't reach the assistant right now."


class ChatContent(Protocol):
    """The shape shared by Home Assistant's SystemContent, UserContent, AssistantContent, and ToolResultContent."""

    role: str
    content: str | None


def chat_log_to_conversation(contents: list[Any]) -> list[Message]:
    """Keep the spoken messages of the conversation. System prompts are ours, not Home Assistant's, and tool bodies from earlier exchanges are not replayed."""
    conversation: list[Message] = []
    for content in contents:
        text = (getattr(content, "content", None) or "").strip()
        if content.role == "user" and text:
            conversation.append(Message(role=Role.USER, content=text))
        elif content.role == "assistant" and text:
            conversation.append(Message(role=Role.ASSISTANT, content=text))
    return conversation


async def agent_events_to_deltas(events: AsyncIterator[AgentEvent], on_done: Callable[[Transcript], None] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Turn the agent's event stream into one streamed assistant message: filler sentence first, then the answer as it arrives.
    A reply that stayed silent on purpose streams no content at all; only an accidental empty reply gets the spoken fallback."""
    yield {"role": "assistant"}
    spoke = False
    stayed_silent = False
    async for event in events:
        if isinstance(event, FillerSpoken):
            spoke = True
            yield {"content": event.text + " "}
        elif isinstance(event, AnswerDelta):
            spoke = True
            yield {"content": event.text}
        elif isinstance(event, Done):
            stayed_silent = event.transcript.stayed_silent
            log_transcript(event.transcript)
            if on_done is not None:
                on_done(event.transcript)
    if not spoke and not stayed_silent:
        yield {"content": EMPTY_ANSWER_FALLBACK}


def log_transcript(transcript: Transcript) -> None:
    _LOGGER.debug(
        "studio_assistant exchange: %.1fs total, first spoken at %s, %d tool calls, truncated=%s, stayed_silent=%s, error=%s",
        transcript.total_seconds,
        f"{transcript.time_to_first_spoken_seconds:.1f}s" if transcript.time_to_first_spoken_seconds is not None else "n/a",
        transcript.tool_call_count,
        transcript.truncated,
        transcript.stayed_silent,
        transcript.error,
    )
    for tool_call_record in transcript.tool_call_records:
        _LOGGER.debug(
            "  tool %s(%s) in %.1fs%s", tool_call_record.call.name, tool_call_record.call.arguments, tool_call_record.seconds, f" error={tool_call_record.error}" if tool_call_record.error else ""
        )


def harness_unreachable(conversation: list[Message], error: str) -> AsyncIterator[AgentEvent]:
    """The events of an answer that says the harness is down, so the user hears why instead of silence (design doc v2/04 section 6)."""
    return events_of(
        AnswerDelta(text=HARNESS_UNREACHABLE_ANSWER),
        Done(transcript=Transcript(model="", system_prompt="", conversation=list(conversation), spoken_text=HARNESS_UNREACHABLE_ANSWER, final_answer=HARNESS_UNREACHABLE_ANSWER, error=error)),
    )


async def events_of(*events: AgentEvent) -> AsyncIterator[AgentEvent]:
    for event in events:
        yield event


MAX_TRACKED_CONVERSATIONS = 32


class FollowUpListening:
    """Decides whether the puck listens for a follow-up after a reply, without a new wake word, and counts the consecutive follow-ups of each conversation.

    Without a cap a false wake can loop: the television triggers the wake word, the assistant answers, the microphone reopens, the television is still
    talking, and the assistant answers it again. Counts live only while a conversation keeps listening; the oldest are dropped past a fixed number of
    conversations, because a follow-up that nobody spoke into ends the conversation without another call here.
    """

    def __init__(self, enabled: bool, max_follow_ups: int) -> None:
        self._enabled = enabled
        self._max_follow_ups = max_follow_ups
        self._follow_up_counts: OrderedDict[str, int] = OrderedDict()

    def record_reply_and_decide(self, conversation_id: str, transcript: Transcript) -> bool:
        """Return whether to listen again after this reply, counting it as a follow-up when the answer is yes and forgetting the conversation when no."""
        keep_listening = self._reply_invites_follow_up(transcript) and self.follow_ups_so_far(conversation_id) < self._max_follow_ups
        if keep_listening:
            self._count_follow_up(conversation_id)
        else:
            self._follow_up_counts.pop(conversation_id, None)
        return keep_listening

    def follow_ups_so_far(self, conversation_id: str) -> int:
        return self._follow_up_counts.get(conversation_id, 0)

    def _reply_invites_follow_up(self, transcript: Transcript) -> bool:
        return self._enabled and not transcript.stayed_silent and not is_acknowledgement(transcript.final_answer)

    def _count_follow_up(self, conversation_id: str) -> None:
        self._follow_up_counts[conversation_id] = self.follow_ups_so_far(conversation_id) + 1
        self._follow_up_counts.move_to_end(conversation_id)
        while len(self._follow_up_counts) > MAX_TRACKED_CONVERSATIONS:
            self._follow_up_counts.popitem(last=False)


def is_acknowledgement(answer: str) -> bool:
    """True for the fixed reply to "never mind", tolerating a dropped period or different case from a small model."""
    return answer.strip().rstrip(".!").casefold() == ACKNOWLEDGEMENT_REPLY.rstrip(".").casefold()
