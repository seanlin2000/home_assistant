"""The conversation entity: Home Assistant's Assist pipeline calls it with the transcript and a chat log, and it streams the agent's spoken answer back."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.httpx_client import get_async_client

from assistant_core import agent_loop
from assistant_core.exchange_record import exchange_record_from_transcript, exchanges_url_from_mcp_url
from assistant_core.llm_client import OllamaClient
from assistant_core.mcp_http import HttpMcpToolBox
from assistant_core.models import AgentEvent, ToolCall, Transcript

from . import adapter
from .const import CONF_CONTINUE_CONVERSATION, CONF_MAX_FOLLOW_UPS, CONF_MCP_URL, CONF_MODEL, CONF_OLLAMA_URL, DEFAULT_CONTINUE_CONVERSATION, DEFAULT_MAX_FOLLOW_UPS, DOMAIN

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
            model="assistant_core agent loop",
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
        """Run the agent loop and stream its spoken answer into the chat log; return the exchange's transcript."""
        settings = {**self.entry.data, **self.entry.options}
        history = adapter.chat_log_to_conversation(chat_log.content)
        # Built off the event loop: the underlying httpx client loads the CA bundle from disk when it is created, which Home Assistant flags as a blocking call.
        llm = await self.hass.async_add_executor_job(OllamaClient, settings[CONF_MODEL], settings[CONF_OLLAMA_URL], "30m")
        policy = adapter.policy_from_settings(settings)
        try:
            async with HttpMcpToolBox(settings[CONF_MCP_URL], client=get_async_client(self.hass), timeout_seconds=policy.tool_timeout_seconds) as tools:
                return await self._stream_events(chat_log, agent_loop.run(history, llm, tools, policy))
        except Exception as error:  # the tool server being down must not silence the assistant
            _LOGGER.warning("studio_assistant: search tool unavailable (%s); answering without it", error)
            return await self._stream_events(chat_log, agent_loop.run(history, llm, UnavailableToolBox(), policy))

    async def _stream_events(self, chat_log: conversation.ChatLog, events: AsyncIterator[AgentEvent]) -> Transcript:
        finished: list[Transcript] = []

        def on_done(transcript: Transcript) -> None:
            finished.append(transcript)
            self._record_exchange(transcript)

        async for _content in chat_log.async_add_delta_content_stream(self.entity_id, adapter.agent_events_to_deltas(events, on_done=on_done)):
            pass
        return finished[-1]

    def _record_exchange(self, transcript: Transcript) -> None:
        """Called when the agent loop finishes an exchange. The post runs as a background task so the spoken answer is never held up by logging."""
        settings = {**self.entry.data, **self.entry.options}
        url = exchanges_url_from_mcp_url(settings[CONF_MCP_URL])
        record = exchange_record_from_transcript(transcript, source="home_assistant")
        self.hass.async_create_background_task(adapter.post_exchange_record(get_async_client(self.hass), url, record), name="studio_assistant exchange record")


class UnavailableToolBox:
    """A tool box with no tools, used when the MCP server cannot be reached so the model answers from knowledge with the loop's caveat."""

    async def list_tools(self) -> list:
        return []

    async def call(self, call: ToolCall) -> str:
        raise ConnectionError("tool server unavailable")
