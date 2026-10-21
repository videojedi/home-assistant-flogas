"""The Flogas integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FlogasAPI, FlogasAuthError, FlogasError
from .const import ATTR_READING, DEFAULT_SCAN_INTERVAL, DOMAIN, SERVICE_SUBMIT_GAUGE

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SUBMIT_GAUGE_SCHEMA = vol.Schema({
    vol.Required(ATTR_READING): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
})

type FlogasConfigEntry = ConfigEntry[FlogasDataUpdateCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""

    async def handle_submit_gauge(call: ServiceCall) -> None:
        """Handle the submit_gauge_reading service call."""
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise HomeAssistantError("No Flogas account is loaded")
        coordinator: FlogasDataUpdateCoordinator = entries[0].runtime_data
        try:
            await coordinator.api.submit_gauge_reading(call.data[ATTR_READING])
        except FlogasError as err:
            raise HomeAssistantError(f"Gauge submission failed: {err}") from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SUBMIT_GAUGE,
        handle_submit_gauge,
        schema=SERVICE_SUBMIT_GAUGE_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FlogasConfigEntry) -> bool:
    """Set up Flogas from a config entry."""
    # Own session so the XSRF cookie jar is not shared with other integrations
    session = aiohttp.ClientSession()
    api = FlogasAPI(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = FlogasDataUpdateCoordinator(hass, entry, api, session)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await session.close()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlogasConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.session.close()
    return unload_ok


class FlogasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Flogas data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FlogasConfigEntry,
        api: FlogasAPI,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize coordinator."""
        self.api = api
        self.session = session
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self.api.get_all_data()
        except FlogasAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FlogasError as err:
            raise UpdateFailed(str(err)) from err
