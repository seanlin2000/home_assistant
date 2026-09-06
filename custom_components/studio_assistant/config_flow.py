"""UI configuration: where Ollama and the search tool live, which model to run, and the loop policy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_CONTEXT_TOKENS,
    CONF_CONTINUE_CONVERSATION,
    CONF_MAX_OUTPUT_TOKENS,
    CONF_MAX_TOOL_ROUNDS,
    CONF_MCP_URL,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_TEMPERATURE,
    CONF_THINK,
    CONF_TOOL_TIMEOUT,
    CONF_WORD_BUDGET,
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_CONTINUE_CONVERSATION,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TOOL_ROUNDS,
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINK,
    DEFAULT_TOOL_TIMEOUT,
    DEFAULT_WORD_BUDGET,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_OLLAMA_URL, default=defaults.get(CONF_OLLAMA_URL, DEFAULT_OLLAMA_URL)): str,
            vol.Required(CONF_MODEL, default=defaults.get(CONF_MODEL, DEFAULT_MODEL)): str,
            vol.Required(CONF_MCP_URL, default=defaults.get(CONF_MCP_URL, DEFAULT_MCP_URL)): str,
        }
    )


def policy_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TEMPERATURE, default=defaults.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)): vol.Coerce(float),
            vol.Optional(CONF_WORD_BUDGET, default=defaults.get(CONF_WORD_BUDGET, DEFAULT_WORD_BUDGET)): vol.Coerce(int),
            vol.Optional(CONF_MAX_TOOL_ROUNDS, default=defaults.get(CONF_MAX_TOOL_ROUNDS, DEFAULT_MAX_TOOL_ROUNDS)): vol.Coerce(int),
            vol.Optional(CONF_CONTEXT_TOKENS, default=defaults.get(CONF_CONTEXT_TOKENS, DEFAULT_CONTEXT_TOKENS)): vol.Coerce(int),
            vol.Optional(CONF_MAX_OUTPUT_TOKENS, default=defaults.get(CONF_MAX_OUTPUT_TOKENS, DEFAULT_MAX_OUTPUT_TOKENS)): vol.Coerce(int),
            vol.Optional(CONF_THINK, default=defaults.get(CONF_THINK, DEFAULT_THINK)): bool,
            vol.Optional(CONF_TOOL_TIMEOUT, default=defaults.get(CONF_TOOL_TIMEOUT, DEFAULT_TOOL_TIMEOUT)): vol.Coerce(float),
            vol.Optional(CONF_CONTINUE_CONVERSATION, default=defaults.get(CONF_CONTINUE_CONVERSATION, DEFAULT_CONTINUE_CONVERSATION)): bool,
        }
    )


class StudioAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(title="Studio Assistant", data=user_input)
        return self.async_show_form(step_id="user", data_schema=connection_schema(user_input or {}), errors=errors)

    async def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        client = get_async_client(self.hass)
        try:
            response = await client.get(f"{user_input[CONF_OLLAMA_URL].rstrip('/')}/api/tags", timeout=10)
            response.raise_for_status()
        except Exception as error:  # any transport or HTTP failure means the URL is wrong for our purposes
            _LOGGER.warning("Ollama not reachable at %s: %s", user_input[CONF_OLLAMA_URL], error)
            return {CONF_OLLAMA_URL: "cannot_connect"}
        models = {item.get("name") or item.get("model") for item in response.json().get("models", [])}
        if user_input[CONF_MODEL] not in models and f"{user_input[CONF_MODEL]}:latest" not in models:
            return {CONF_MODEL: "model_not_found"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StudioAssistantOptionsFlow()


class StudioAssistantOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=policy_schema(dict(self.config_entry.options)))
