"""The conversation entity: Home Assistant's Assist pipeline calls it with the transcript and a chat log, and it streams the agent's spoken answer back."""

from __future__ import annotations

import logging
from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.httpx_client import get_async_client

from assistant_core import agent_loop
from assistant_core.llm_client import OllamaClient
from assistant_core.mcp_http import HttpMcpToolBox

from . import adapter
from .const import CONF_CONTINUE_CONVERSATION, CONF_MCP_URL, CONF_MODEL, CONF_OLLAMA_URL, DEFAULT_CONTINUE_CONVERSATION, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([StudioAssistantEntity(entry)])


class StudioAssistantEntity(conversation.ConversationEntity):
    """One agent per config entry. Statelessness is deliberate: the chat log carries the history, exactly as the benchmark's two-turn question does."""

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
        settings = {**self.entry.data, **self.entry.options}
        history = adapter.chat_log_to_conversation(chat_log.content)
        llm = OllamaClient(settings[CONF_MODEL], host=settings[CONF_OLLAMA_URL], keep_alive="30m")
        policy = adapter.policy_from_settings(settings)
        try:
            async with HttpMcpToolBox(settings[CONF_MCP_URL], client=get_async_client(self.hass), timeout_seconds=policy.tool_timeout_seconds) as tools:
                events = agent_loop.run(history, llm, tools, policy)
                async for _content in chat_log.async_add_delta_content_stream(self.entity_id, adapter.agent_events_to_deltas(events)):
                    pass
        except Exception as error:  # the tool server being down must not silence the assistant
            _LOGGER.warning("studio_assistant: search tool unavailable (%s); answering without it", error)
            events = agent_loop.run(history, llm, UnavailableToolBox(), policy)
            async for _content in chat_log.async_add_delta_content_stream(self.entity_id, adapter.agent_events_to_deltas(events)):
                pass
        result = conversation.async_get_result_from_chat_log(user_input, chat_log)
        if settings.get(CONF_CONTINUE_CONVERSATION, DEFAULT_CONTINUE_CONVERSATION):
            return conversation.ConversationResult(response=result.response, conversation_id=result.conversation_id, continue_conversation=True)
        return result


class UnavailableToolBox:
    """A tool box with no tools, used when the MCP server cannot be reached so the model answers from knowledge with the loop's caveat."""

    async def list_tools(self) -> list:
        return []

    async def call(self, call) -> str:
        raise ConnectionError("tool server unavailable")
