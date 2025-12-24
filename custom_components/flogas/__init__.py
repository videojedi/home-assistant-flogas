"""The Flogas integration."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    API_DATA_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGIN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class FlogasAPI:
    """API client for Flogas portal."""

    def __init__(self, email: str, password: str) -> None:
        """Initialize the API client."""
        self.email = email
        self.password = password
        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.5",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def login(self) -> bool:
        """Authenticate with the Flogas portal and get token."""
        try:
            session = await self._get_session()
            
            # First, get the login page to get any CSRF token
            async with session.get(LOGIN_URL) as response:
                if response.status != 200:
                    raise ConfigEntryAuthFailed(f"Failed to get login page: {response.status}")
                html = await response.text()
            
            # Extract CSRF token from the page
            csrf_match = re.search(r'name="_token"\s+value="([^"]+)"', html)
            if not csrf_match:
                csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
            
            csrf_token = csrf_match.group(1) if csrf_match else ""
            
            # Submit login
            login_data = {
                "_token": csrf_token,
                "email": self.email,
                "password": self.password,
            }
            
            async with session.post(
                LOGIN_URL, data=login_data, allow_redirects=True
            ) as response:
                if response.status != 200:
                    raise ConfigEntryAuthFailed(f"Login failed with status: {response.status}")
            
            # Get the overview page which should have the token
            async with session.get("https://myaccount.flogas.co.uk/overview") as response:
                if response.status != 200:
                    raise ConfigEntryAuthFailed("Failed to access dashboard after login")
                html = await response.text()
            
            # Look for the API token in the page source
            token_match = re.search(r'"token"\s*:\s*"([^"]+)"', html)
            if not token_match:
                token_match = re.search(r"localStorage\.setItem\(['\"]token['\"]\s*,\s*['\"]([^'\"]+)['\"]", html)
            
            if token_match:
                self._token = token_match.group(1)
                _LOGGER.debug("Successfully obtained API token")
                return True
            
            # Try making an API call with session cookies
            test_data = await self._fetch_data_with_session(session)
            if test_data:
                _LOGGER.debug("Session authentication successful")
                return True
                
            raise ConfigEntryAuthFailed("Could not obtain API token after login")

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error during login: {err}") from err

    async def _fetch_data_with_session(self, session: aiohttp.ClientSession) -> dict | None:
        """Try to fetch data using session cookies."""
        headers = {
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            
        try:
            async with session.get(API_DATA_URL, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        return data.get("response", {})
        except Exception:
            pass
        return None

    async def get_tank_data(self) -> dict:
        """Fetch tank data from the API."""
        try:
            session = await self._get_session()
            
            headers = {
                "Accept": "application/json",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            
            async with session.get(API_DATA_URL, headers=headers) as response:
                if response.status == 401 or response.status == 403:
                    _LOGGER.debug("Session expired, attempting re-login")
                    await self.login()
                    if self._token:
                        headers["Authorization"] = f"Bearer {self._token}"
                    async with session.get(API_DATA_URL, headers=headers) as retry_response:
                        if retry_response.status != 200:
                            raise UpdateFailed(f"Failed to get data after re-login: {retry_response.status}")
                        data = await retry_response.json()
                elif response.status != 200:
                    raise UpdateFailed(f"Failed to get tank data: {response.status}")
                else:
                    data = await response.json()
            
            if not data.get("success"):
                errors = data.get("errors", ["Unknown error"])
                raise UpdateFailed(f"API error: {errors}")
            
            response_data = data.get("response", {})
            
            return {
                "tank_capacity": response_data.get("tankCapacity"),
                "remaining_percentage": response_data.get("remainingPercentage"),
                "days_remaining": response_data.get("daysRemaining"),
                "last_reading_date": response_data.get("lastGaugeReadingDate"),
                "last_reading_date_iso": response_data.get("lastGaugeReadingDateIso"),
                "min_order_litres": response_data.get("minLitres"),
                "max_order_litres": response_data.get("maxLitres"),
            }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error fetching tank data: {err}") from err

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flogas from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = FlogasAPI(email, password)

    try:
        await api.login()
    except ConfigEntryAuthFailed:
        await api.close()
        raise

    coordinator = FlogasDataUpdateCoordinator(
        hass,
        api=api,
        update_interval=DEFAULT_SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: FlogasDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()

    return unload_ok


class FlogasDataUpdateCoordinator(DataUpdateCoordinator):
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
        return await self.api.get_tank_data()
