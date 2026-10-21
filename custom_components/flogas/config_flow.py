"""Config flow for Flogas integration."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import FlogasAPI, FlogasAuthError, FlogasConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
STEP_REAUTH_DATA_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def _validate_login(account_reference: str, password: str) -> str | None:
    """Try to log in. Returns an error key, or None on success."""
    async with aiohttp.ClientSession() as session:
        try:
            await FlogasAPI(session, account_reference, password).login()
        except FlogasAuthError:
            return "invalid_auth"
        except FlogasConnectionError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error logging in to Flogas")
            return "unknown"
    return None


class FlogasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flogas."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            error = await _validate_login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(
                    title=f"Flogas ({user_input[CONF_EMAIL]})",
                    data=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthorization."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password and check it."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error = await _validate_login(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={"account": entry.data[CONF_EMAIL]},
            errors=errors,
        )
