"""The Flogas integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from http.cookies import SimpleCookie

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
    API_BASE_URL,
    API_DATA_URL,
    CSRF_COOKIE_URL,
    LOGIN_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
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
            jar = aiohttp.CookieJar()
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": "en-GB,en;q=0.5",
                }
            )
        return self._session

    async def login(self) -> bool:
        """Authenticate with the Flogas portal using Laravel Sanctum."""
        try:
            session = await self._get_session()
            
            # Step 1: Get CSRF cookie from sanctum endpoint
            _LOGGER.debug("Fetching CSRF cookie from %s", CSRF_COOKIE_URL)
            async with session.get(CSRF_COOKIE_URL) as response:
                if response.status != 204:
                    raise ConfigEntryAuthFailed(f"Failed to get CSRF cookie: {response.status}")
            
            # Step 2: Extract XSRF-TOKEN from cookies
            xsrf_token = None
            for cookie in session.cookie_jar:
                if cookie.key == "XSRF-TOKEN":
                    # URL decode the token (it's URL encoded in the cookie)
                    import urllib.parse
                    xsrf_token = urllib.parse.unquote(cookie.value)
                    break
            
            if not xsrf_token:
                raise ConfigEntryAuthFailed("XSRF-TOKEN cookie not found")
            
            _LOGGER.debug("Got XSRF token, attempting login")
            
            # Step 3: POST login with credentials and XSRF token header
            login_data = {
                "email": self.email,
                "password": self.password,
            }
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-XSRF-TOKEN": xsrf_token,
            }
            
            async with session.post(
                LOGIN_URL, 
                json=login_data, 
                headers=headers
            ) as response:
                data = await response.json()
                
                if response.status == 419:
                    raise ConfigEntryAuthFailed("CSRF token mismatch - authentication failed")
                
                if not data.get("success"):
                    errors = data.get("errors", {})
                    if "credentials" in str(errors).lower() or "email" in errors or "password" in errors:
                        raise ConfigEntryAuthFailed("Invalid email or password")
                    raise ConfigEntryAuthFailed(f"Login failed: {errors}")
                
                # Extract token from response
                response_data = data.get("response", {})
                self._token = response_data.get("token")
                
                if not self._token:
                    # Token might be in cookies or different location
                    _LOGGER.warning("Token not in response, checking session")
                
                _LOGGER.debug("Successfully logged in to Flogas portal")
                return True

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error during login: {err}") from err

    async def get_tank_data(self) -> dict:
        """Fetch tank data from the API."""
        try:
            session = await self._get_session()
            
            headers = {
                "Accept": "application/json",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            
            # Get XSRF token for the request
            xsrf_token = None
            for cookie in session.cookie_jar:
                if cookie.key == "XSRF-TOKEN":
                    import urllib.parse
                    xsrf_token = urllib.parse.unquote(cookie.value)
                    headers["X-XSRF-TOKEN"] = xsrf_token
                    break
            
            async with session.get(API_DATA_URL, headers=headers) as response:
                if response.status in [401, 403, 419]:
                    _LOGGER.debug("Session expired, attempting re-login")
                    await self.login()
                    # Update headers with new token
                    if self._token:
                        headers["Authorization"] = f"Bearer {self._token}"
                    for cookie in session.cookie_jar:
                        if cookie.key == "XSRF-TOKEN":
                            import urllib.parse
                            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(cookie.value)
                            break
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
