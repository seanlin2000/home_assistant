"""Pure translation between Home Assistant's chat log vocabulary and assistant_core's, kept free of Home Assistant imports so it is unit-testable in the project venv.

Home Assistant hands the agent a chat log of typed content objects and expects a stream of delta dictionaries back. assistant_core speaks Message
objects in and AgentEvent objects out. Everything the entity does is these two conversions, the policy mapping, and the decision whether to listen
for a follow-up.
"""

import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

import httpx

from assistant_core.exchange_record import ExchangeRecord
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, FillerSpoken, Message, Role, Transcript
from assistant_core.prompts import ACKNOWLEDGEMENT_REPLY

_LOGGER = logging.getLogger(__name__)

EMPTY_ANSWER_FALLBACK = "Sorry, I could not come up with an answer to that."


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


EXCHANGE_RECORD_TIMEOUT_SECONDS = 3.0


async def post_exchange_record(client: httpx.AsyncClient, url: str, record: ExchangeRecord, timeout: float = EXCHANGE_RECORD_TIMEOUT_SECONDS) -> bool:
    """Send one exchange's record to the tool server's /exchanges route (design doc 10 §3.4). Best effort: every failure is logged at debug level and swallowed,
    because a missing log line must never cost the user an answer or a warning in Home Assistant's log."""
    try:
        response = await client.post(url, content=record.model_dump_json(), headers={"content-type": "application/json"}, timeout=timeout)
    except Exception as error:  # noqa: BLE001 - anything from a refused connection to a cancelled loop
        _LOGGER.debug("studio_assistant: exchange record not posted to %s (%s)", url, error)
        return False
    if response.status_code != 204:
        _LOGGER.debug("studio_assistant: exchange record rejected by %s with %s: %s", url, response.status_code, response.text[:200])
        return False
    return True


def policy_from_settings(settings: dict[str, Any], defaults: AgentPolicy | None = None) -> AgentPolicy:
    """Build the loop policy from the config entry's merged data and options, falling back to the core defaults for anything unset."""
    base = defaults or AgentPolicy()
    return base.model_copy(
        update={
            "temperature": float(settings.get("temperature", base.temperature)),
            "word_budget": int(settings.get("word_budget", base.word_budget)),
            "max_tool_rounds": int(settings.get("max_tool_rounds", base.max_tool_rounds)),
            "context_tokens": int(settings.get("context_tokens", base.context_tokens)),
            "max_output_tokens": int(settings.get("max_output_tokens", base.max_output_tokens)),
            "think": settings.get("think", base.think),
            "tool_timeout_seconds": float(settings.get("tool_timeout_seconds", base.tool_timeout_seconds)),
        }
    )


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
