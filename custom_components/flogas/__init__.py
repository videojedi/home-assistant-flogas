"""The Flogas integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
import urllib.parse

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_SUBMIT_GAUGE = "submit_gauge_reading"
ATTR_READING = "reading"

SERVICE_SUBMIT_GAUGE_SCHEMA = vol.Schema({
    vol.Required(ATTR_READING): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
})

API_BASE_URL = "https://datalayer.flogas.co.uk"
API_CSRF_URL = f"{API_BASE_URL}/sanctum/csrf-cookie"
API_LOGIN_URL = f"{API_BASE_URL}/portal/customer/login"
API_DATA_URL = f"{API_BASE_URL}/portal/overview/data-bulk"
API_CUSTOMER_URL = f"{API_BASE_URL}/portal/customer"
API_GAUGE_URL = f"{API_BASE_URL}/portal/bulk/gauge"

# Browser-like headers required by the Flogas portal
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://myaccount.flogas.co.uk/",
    "Origin": "https://myaccount.flogas.co.uk",
}


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

    # Register services
    async def handle_submit_gauge(call: ServiceCall) -> None:
        """Handle the submit_gauge_reading service call."""
        reading = call.data[ATTR_READING]
        _LOGGER.debug("Service called: submit_gauge_reading with reading=%d", reading)

        # Use the first available coordinator's API
        for coord in hass.data[DOMAIN].values():
            if hasattr(coord, "api"):
                result = await coord.api.submit_gauge_reading(reading)
                if result.get("success"):
                    # Refresh data after successful submission
                    await coord.async_request_refresh()
                return

    # Only register service once (not per entry)
    if not hass.services.has_service(DOMAIN, SERVICE_SUBMIT_GAUGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SUBMIT_GAUGE,
            handle_submit_gauge,
            schema=SERVICE_SUBMIT_GAUGE_SCHEMA,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class FlogasAPI:
    """Flogas API client."""

    def __init__(self, email: str, password: str) -> None:
        """Initialize the API."""
        self._email = email
        self._password = password
        self._token: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._logged_in: bool = False

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an aiohttp session with the required headers."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=_DEFAULT_HEADERS)
        return self._session

    def _get_xsrf_token(self) -> str | None:
        """Extract the XSRF-TOKEN cookie value from the session jar."""
        if self._session is None:
            return None
        for cookie in self._session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                return urllib.parse.unquote(cookie.value)
        return None

    async def login(self) -> bool:
        """Login to the Flogas API and obtain a bearer token."""
        session = await self._ensure_session()
        self._logged_in = False
        self._token = None

        # Step 1: Fetch CSRF cookie (Laravel Sanctum handshake)
        try:
            async with session.get(API_CSRF_URL) as response:
                if response.status not in (200, 204):
                    _LOGGER.error(
                        "Failed to get CSRF cookie: HTTP %s", response.status
                    )
                    return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error fetching CSRF cookie: %s", err)
            return False

        # Step 2: Extract XSRF token
        xsrf_token = self._get_xsrf_token()
        if not xsrf_token:
            _LOGGER.error("No XSRF-TOKEN cookie received after CSRF handshake")
            return False

        # Step 3: POST login credentials
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf_token,
        }
        payload = {
            "accountReference": self._email,
            "password": self._password,
        }

        try:
            async with session.post(
                API_LOGIN_URL, json=payload, headers=headers
            ) as response:
                result = await response.json(content_type=None)

                if response.status != 200 or not result.get("success"):
                    _LOGGER.error(
                        "Login failed (HTTP %s): %s", response.status, result
                    )
                    return False

                self._token = result.get("response", {}).get("token")
                if not self._token:
                    _LOGGER.error("Login response contained no token: %s", result)
                    return False

                self._logged_in = True
                _LOGGER.debug(
                    "Login successful, token: %s…", self._token[:20]
                )
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during login: %s", err)
            return False

    def _auth_headers(self) -> dict[str, str]:
        """Build authorisation headers for authenticated requests."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        xsrf = self._get_xsrf_token()
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        return headers

    async def _ensure_logged_in(self) -> None:
        """Login if we don't already have a valid token."""
        if not self._logged_in or not self._token:
            if not await self.login():
                raise UpdateFailed("Failed to authenticate with Flogas API")

    async def get_tank_data(self) -> dict[str, Any]:
        """Get tank data from the API."""
        await self._ensure_logged_in()
        session = await self._ensure_session()

        async with session.get(
            API_DATA_URL, headers=self._auth_headers()
        ) as response:
            if response.status in (401, 403, 419):
                _LOGGER.debug("Session expired, re-logging in")
                self._logged_in = False
                await self._ensure_logged_in()
                # Retry once after re-auth
                async with session.get(
                    API_DATA_URL, headers=self._auth_headers()
                ) as retry:
                    if retry.status != 200:
                        raise UpdateFailed(
                            f"Error fetching tank data after re-auth: HTTP {retry.status}"
                        )
                    result = await retry.json(content_type=None)
            elif response.status != 200:
                raise UpdateFailed(
                    f"Error fetching tank data: HTTP {response.status}"
                )
            else:
                result = await response.json(content_type=None)

        if not result.get("success"):
            raise UpdateFailed(f"Tank data API error: {result}")

        data = result.get("response", {}).get("data", {})

        # Calculate days remaining locally if the API returns null
        # averageDailyUsage is in percentage points per day, so divide
        # remainingPercentage directly by it (no need to involve tank capacity)
        days_remaining = data.get("daysRemaining")
        if days_remaining is None:
            try:
                remaining_pct = data.get("remainingPercentage")
                daily_usage = data.get("averageDailyUsage")
                if remaining_pct and daily_usage:
                    days_remaining = round(remaining_pct / daily_usage)
            except (TypeError, ZeroDivisionError):
                pass

        return {
            "remaining_percentage": data.get("remainingPercentage"),
            "days_remaining": days_remaining,
            "tank_capacity": data.get("tankCapacity"),
            "last_reading_date": data.get("lastGaugeReadingDate"),
        }

    async def get_customer_data(self) -> dict[str, Any]:
        """Get customer data including balance from the API."""
        await self._ensure_logged_in()
        session = await self._ensure_session()

        async with session.get(
            API_CUSTOMER_URL, headers=self._auth_headers()
        ) as response:
            if response.status in (401, 403, 419):
                _LOGGER.debug("Session expired, re-logging in for customer data")
                self._logged_in = False
                await self._ensure_logged_in()
                async with session.get(
                    API_CUSTOMER_URL, headers=self._auth_headers()
                ) as retry:
                    if retry.status != 200:
                        _LOGGER.warning(
                            "Error fetching customer data after re-auth: HTTP %s",
                            retry.status,
                        )
                        return {}
                    result = await retry.json(content_type=None)
            elif response.status != 200:
                _LOGGER.warning(
                    "Error fetching customer data: HTTP %s", response.status
                )
                return {}
            else:
                result = await response.json(content_type=None)

        if not result.get("success"):
            _LOGGER.warning("Customer API error: %s", result)
            return {}

        customer = result.get("response", {}).get("customer", {})
        return {"balance": customer.get("balance")}

    async def get_all_data(self) -> dict[str, Any]:
        """Get all data from both tank and customer endpoints."""
        tank_data = await self.get_tank_data()
        customer_data = await self.get_customer_data()
        return {**tank_data, **customer_data}

    async def submit_gauge_reading(self, reading: int) -> dict[str, Any]:
        """Submit a tank gauge reading to Flogas.

        Args:
            reading: Tank level as a percentage (0-100).

        Returns:
            API response dict with success status.
        """
        if not 0 <= reading <= 100:
            raise ValueError("Reading must be between 0 and 100")

        await self._ensure_logged_in()
        session = await self._ensure_session()

        headers = {**self._auth_headers(), "Content-Type": "application/json"}

        async with session.post(
            API_GAUGE_URL, json={"reading": reading}, headers=headers
        ) as response:
            if response.status in (401, 403, 419):
                _LOGGER.debug("Session expired, re-logging in for gauge submission")
                self._logged_in = False
                await self._ensure_logged_in()
                return await self.submit_gauge_reading(reading)

            result = await response.json(content_type=None)

            if response.status != 200 or not result.get("success"):
                _LOGGER.error(
                    "Gauge submission failed (HTTP %s): %s", response.status, result
                )
                return {"success": False, "error": result}

            _LOGGER.info("Successfully submitted gauge reading: %d%%", reading)
            return {"success": True, "response": result.get("response", {})}

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


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
