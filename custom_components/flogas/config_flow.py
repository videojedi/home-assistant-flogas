"""Config flow for Flogas integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from . import FlogasAPI

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class FlogasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flogas."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = FlogasAPI(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            
            try:
                await api.login()
                await api.close()
                
                await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"Flogas ({user_input[CONF_EMAIL]})",
                    data=user_input,
                )
            except Exception as err:
                _LOGGER.error("Failed to authenticate with Flogas: %s", err)
                errors["base"] = "invalid_auth"
            finally:
                await api.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthorization."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthorization confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = FlogasAPI(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            
            try:
                await api.login()
                
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=user_input,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except Exception:
                errors["base"] = "invalid_auth"
            finally:
                await api.close()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
