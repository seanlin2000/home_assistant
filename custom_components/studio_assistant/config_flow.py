"""UI configuration: where the harness listens and its API key, and whether the puck listens for a follow-up. Everything that shapes an answer lives
in the harness's own config on the Mac (design doc v2/04 section 3.2)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client

from assistant_core.harness_client import HarnessClient

from .const import CONF_CONTINUE_CONVERSATION, CONF_HARNESS_API_KEY, CONF_HARNESS_URL, CONF_MAX_FOLLOW_UPS, DEFAULT_CONTINUE_CONVERSATION, DEFAULT_HARNESS_URL, DEFAULT_MAX_FOLLOW_UPS, DOMAIN

_LOGGER = logging.getLogger(__name__)


def connection_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HARNESS_URL, default=defaults.get(CONF_HARNESS_URL, DEFAULT_HARNESS_URL)): str,
            vol.Required(CONF_HARNESS_API_KEY, default=defaults.get(CONF_HARNESS_API_KEY, "")): str,
        }
    )


def options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_HARNESS_URL, default=defaults.get(CONF_HARNESS_URL, DEFAULT_HARNESS_URL)): str,
            vol.Optional(CONF_HARNESS_API_KEY, default=defaults.get(CONF_HARNESS_API_KEY, "")): str,
            vol.Optional(CONF_CONTINUE_CONVERSATION, default=defaults.get(CONF_CONTINUE_CONVERSATION, DEFAULT_CONTINUE_CONVERSATION)): bool,
            vol.Optional(CONF_MAX_FOLLOW_UPS, default=defaults.get(CONF_MAX_FOLLOW_UPS, DEFAULT_MAX_FOLLOW_UPS)): vol.Coerce(int),
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
        client = HarnessClient(user_input[CONF_HARNESS_URL], user_input[CONF_HARNESS_API_KEY], client=get_async_client(self.hass))
        try:
            await client.health()
        except httpx.HTTPStatusError as error:
            _LOGGER.warning("the harness at %s refused the key: %s", user_input[CONF_HARNESS_URL], error)
            return {CONF_HARNESS_API_KEY: "invalid_auth"}
        except Exception as error:  # any transport failure means the address is wrong for our purposes
            _LOGGER.warning("the harness is not reachable at %s: %s", user_input[CONF_HARNESS_URL], error)
            return {CONF_HARNESS_URL: "cannot_connect"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StudioAssistantOptionsFlow()


class StudioAssistantOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=options_schema({**self.config_entry.data, **self.config_entry.options}))
