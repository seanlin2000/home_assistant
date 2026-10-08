"""The conversation entity: Home Assistant's Assist pipeline calls it with the transcript and a chat log; it sends the conversation to the harness on
the Mac and streams the spoken answer back (design doc v2/04 section 3.2)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Literal

import httpx
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.httpx_client import get_async_client

from assistant_core.converse_protocol import ConverseRequest
from assistant_core.harness_client import HarnessClient
from assistant_core.models import AgentEvent, Transcript

from . import adapter
from .const import CONF_CONTINUE_CONVERSATION, CONF_HARNESS_API_KEY, CONF_HARNESS_URL, CONF_MAX_FOLLOW_UPS, DEFAULT_CONTINUE_CONVERSATION, DEFAULT_MAX_FOLLOW_UPS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([StudioAssistantEntity(entry)])


class StudioAssistantEntity(conversation.ConversationEntity):
    """One agent per config entry. The chat log carries the history, exactly as the benchmark's two-exchange questions do; the only state kept here is
    the follow-up count of each conversation. A change of options reloads the entry, which builds a new entity with the new settings."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="studio_assistant",
            model="assistant harness client",
            entry_type=DeviceEntryType.SERVICE,
        )
        settings = {**entry.data, **entry.options}
        self._follow_up_listening = adapter.FollowUpListening(
            enabled=bool(settings.get(CONF_CONTINUE_CONVERSATION, DEFAULT_CONTINUE_CONVERSATION)),
            max_follow_ups=int(settings.get(CONF_MAX_FOLLOW_UPS, DEFAULT_MAX_FOLLOW_UPS)),
        )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return ["en"]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        settings = {**self.entry.data, **self.entry.options}
        self._harness = HarnessClient(settings[CONF_HARNESS_URL], settings[CONF_HARNESS_API_KEY], client=get_async_client(self.hass))
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(self, user_input: conversation.ConversationInput, chat_log: conversation.ChatLog) -> conversation.ConversationResult:
        transcript = await self._stream_answer_into(chat_log)
        if chat_log.content[-1].role != "assistant":
            # A silent reply streams nothing. Home Assistant's result builder raises when the log does not end with an assistant entry, which the puck
            # would announce as an error; an empty entry gives it empty speech instead, and the pipeline then skips text to speech.
            chat_log.async_add_assistant_content_without_tools(conversation.AssistantContent(agent_id=self.entity_id, content=None))
        result = conversation.async_get_result_from_chat_log(user_input, chat_log)
        keep_listening = self._follow_up_listening.record_reply_and_decide(result.conversation_id, transcript)
        return conversation.ConversationResult(response=result.response, conversation_id=result.conversation_id, continue_conversation=keep_listening)

    async def _stream_answer_into(self, chat_log: conversation.ChatLog) -> Transcript:
        """Ask the harness and stream its spoken answer into the chat log; return the exchange's transcript."""
        history = adapter.chat_log_to_conversation(chat_log.content)
        request = ConverseRequest(conversation_id=chat_log.conversation_id, conversation=history)
        try:
            return await self._stream_events(chat_log, self._harness.converse(request))
        except httpx.HTTPError as error:  # the harness being down must not silence the assistant
            _LOGGER.warning("studio_assistant: harness unavailable (%s)", error)
            return await self._stream_events(chat_log, adapter.harness_unreachable(history, str(error)))

    async def _stream_events(self, chat_log: conversation.ChatLog, events: AsyncIterator[AgentEvent]) -> Transcript:
        finished: list[Transcript] = []
        async for _content in chat_log.async_add_delta_content_stream(self.entity_id, adapter.agent_events_to_deltas(events, on_done=finished.append)):
            pass
        return finished[-1]
