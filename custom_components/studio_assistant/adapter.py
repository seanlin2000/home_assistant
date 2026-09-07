"""Pure translation between Home Assistant's chat log vocabulary and assistant_core's, kept free of Home Assistant imports so it is unit-testable in the project venv.

Home Assistant hands the agent a chat log of typed content objects and expects a stream of delta dictionaries back. assistant_core speaks Message
objects in and AgentEvent objects out. Everything the entity does is these two conversions plus the policy mapping.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, FillerSpoken, Message, Role, Transcript
from assistant_core.turn_record import TurnRecord

_LOGGER = logging.getLogger(__name__)

EMPTY_ANSWER_FALLBACK = "Sorry, I could not come up with an answer to that."


class ChatContent(Protocol):
    """The shape shared by Home Assistant's SystemContent, UserContent, AssistantContent, and ToolResultContent."""

    role: str
    content: str | None


def chat_log_to_conversation(contents: list[Any]) -> list[Message]:
    """Keep the spoken turns of the conversation. System prompts are ours, not Home Assistant's, and tool bodies from earlier turns are not replayed."""
    conversation: list[Message] = []
    for content in contents:
        text = (getattr(content, "content", None) or "").strip()
        if content.role == "user" and text:
            conversation.append(Message(role=Role.USER, content=text))
        elif content.role == "assistant" and text:
            conversation.append(Message(role=Role.ASSISTANT, content=text))
    return conversation


async def agent_events_to_deltas(events: AsyncIterator[AgentEvent], on_done=None) -> AsyncIterator[dict[str, Any]]:
    """Turn the agent's event stream into one streamed assistant message: filler sentence first, then the answer as it arrives."""
    yield {"role": "assistant"}
    spoke = False
    async for event in events:
        if isinstance(event, FillerSpoken):
            spoke = True
            yield {"content": event.text + " "}
        elif isinstance(event, AnswerDelta):
            spoke = True
            yield {"content": event.text}
        elif isinstance(event, Done):
            log_transcript(event.transcript)
            if on_done is not None:
                on_done(event.transcript)
    if not spoke:
        yield {"content": EMPTY_ANSWER_FALLBACK}


def log_transcript(transcript: Transcript) -> None:
    _LOGGER.debug(
        "studio_assistant turn: %.1fs total, first spoken at %s, %d tool calls, truncated=%s, error=%s",
        transcript.total_seconds,
        f"{transcript.time_to_first_spoken_seconds:.1f}s" if transcript.time_to_first_spoken_seconds is not None else "n/a",
        transcript.tool_call_count,
        transcript.truncated,
        transcript.error,
    )
    for exchange in transcript.tool_exchanges:
        _LOGGER.debug("  tool %s(%s) in %.1fs%s", exchange.call.name, exchange.call.arguments, exchange.seconds, f" error={exchange.error}" if exchange.error else "")


TURN_RECORD_TIMEOUT_SECONDS = 3.0


async def post_turn_record(client: httpx.AsyncClient, url: str, record: TurnRecord, timeout: float = TURN_RECORD_TIMEOUT_SECONDS) -> bool:
    """Send one turn's record to the tool server's /turns route (design doc 10 §3.4). Best effort: every failure is logged at debug level and swallowed,
    because a missing log line must never cost the user an answer or a warning in Home Assistant's log."""
    try:
        response = await client.post(url, content=record.model_dump_json(), headers={"content-type": "application/json"}, timeout=timeout)
    except Exception as error:  # noqa: BLE001 - anything from a refused connection to a cancelled loop
        _LOGGER.debug("studio_assistant: turn record not posted to %s (%s)", url, error)
        return False
    if response.status_code != 204:
        _LOGGER.debug("studio_assistant: turn record rejected by %s with %s: %s", url, response.status_code, response.text[:200])
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
