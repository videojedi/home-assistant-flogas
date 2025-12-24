"""The Flogas integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
import urllib.parse

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

API_BASE_URL = "https://datalayer.flogas.co.uk"
API_CSRF_URL = f"{API_BASE_URL}/sanctum/csrf-cookie"
API_LOGIN_URL = f"{API_BASE_URL}/portal/customer/login"
API_DATA_URL = f"{API_BASE_URL}/portal/bulk/data"
API_CUSTOMER_URL = f"{API_BASE_URL}/portal/customer"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flogas from a config entry."""
    api = FlogasAPI(
        entry.data["email"],
        entry.data["password"],
    )

    coordinator = FlogasDataUpdateCoordinator(
        hass,
        api=api,
        update_interval=timedelta(hours=1),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class FlogasAPI:
    """Flogas API client."""

    def __init__(self, account_reference: str, password: str) -> None:
        """Initialize the API."""
        self._account_reference = account_reference
        self._password = password
        self._token: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def login(self) -> bool:
        """Login to the Flogas API."""
        session = await self._ensure_session()

        # Get CSRF cookie
        async with session.get(API_CSRF_URL) as response:
            if response.status != 204:
                _LOGGER.error("Failed to get CSRF cookie: %s", response.status)
                return False

        # Get XSRF token from cookies
        xsrf_token = None
        for cookie in session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                xsrf_token = urllib.parse.unquote(cookie.value)
                break

        if not xsrf_token:
            _LOGGER.error("No XSRF token found in cookies")
            return False

        # Login
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
        }
        data = {
            "accountReference": self._account_reference,
            "password": self._password,
        }

        async with session.post(API_LOGIN_URL, json=data, headers=headers) as response:
            if response.status != 200:
                result = await response.json()
                _LOGGER.error("Login failed: %s", result)
                return False

            result = await response.json()
            if result.get("success"):
                self._token = result.get("response", {}).get("token")
                _LOGGER.debug("Login successful, token: %s...", self._token[:20] if self._token else None)
                return True
            else:
                _LOGGER.error("Login failed: %s", result)
                return False

    async def get_tank_data(self) -> dict[str, Any]:
        """Get tank data from the API."""
        session = await self._ensure_session()

        headers = {
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        # Get XSRF token for the request
        for cookie in session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                headers["X-XSRF-TOKEN"] = urllib.parse.unquote(cookie.value)
                break

        async with session.get(API_DATA_URL, headers=headers) as response:
            if response.status in [401, 403, 419]:
                _LOGGER.debug("Session expired, attempting re-login")
                await self.login()
                return await self.get_tank_data()

            if response.status != 200:
                raise UpdateFailed(f"Error fetching data: {response.status}")

            result = await response.json()

            if not result.get("success"):
                raise UpdateFailed(f"API error: {result}")

            data = result.get("response", {})
            return {
                "remaining_percentage": data.get("remainingPercentage"),
                "days_remaining": data.get("daysRemaining"),
                "tank_capacity": data.get("tankCapacity"),
                "last_reading_date": data.get("lastGaugeReadingDate"),
            }

    async def get_customer_data(self) -> dict[str, Any]:
        """Get customer data including balance from the API."""
        session = await self._ensure_session()

        headers = {
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        # Get XSRF token for the request
        for cookie in session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                headers["X-XSRF-TOKEN"] = urllib.parse.unquote(cookie.value)
                break

        async with session.get(API_CUSTOMER_URL, headers=headers) as response:
            if response.status in [401, 403, 419]:
                _LOGGER.debug("Session expired, attempting re-login")
                await self.login()
                return await self.get_customer_data()

            if response.status != 200:
                _LOGGER.warning("Error fetching customer data: %s", response.status)
                return {}

            result = await response.json()

            if not result.get("success"):
                _LOGGER.warning("Customer API error: %s", result)
                return {}

            customer = result.get("response", {}).get("customer", {})
            return {
                "balance": customer.get("balance"),
            }

    async def get_all_data(self) -> dict[str, Any]:
        """Get all data from both tank and customer endpoints."""
        tank_data = await self.get_tank_data()
        customer_data = await self.get_customer_data()
        
        # Merge the data
        return {**tank_data, **customer_data}

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()


class FlogasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Flogas data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: FlogasAPI,
        update_interval: timedelta,
    ) -> None:
        """Initialize coordinator."""
        self.api = api

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        return await self.api.get_all_data()
