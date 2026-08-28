"""Support for Flogas sensors."""
from datetime import timedelta
import logging
import urllib.parse
import requests

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    BASE_WEB_URL,
    API_BASE_URL,
    LOGIN_URL,
    CSRF_URL,
    DATA_URL,
    CONF_USERNAME,
    CONF_PASSWORD,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(hours=4)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Flogas sensors from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    coordinator = FlogasDataCoordinator(hass, username, password)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        FlogasTankPercentageSensor(coordinator),
        FlogasTankCapacitySensor(coordinator),
        FlogasDailyUsageSensor(coordinator),
        FlogasLastReadingDateSensor(coordinator),
    ], True)


class FlogasDataCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch telemetry data from Flogas API."""

    def __init__(self, hass, username, password):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Flogas Sensor",
            update_interval=SCAN_INTERVAL,
        )
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": BASE_WEB_URL,
            "Referer": f"{BASE_WEB_URL}/",
            "Content-Type": "application/json",
        })

    def _fetch_data(self):
        """Perform login and pull current overview bulk data synchronously."""
        # 1. Initialize CSRF
        self.session.get(BASE_WEB_URL)
        self.session.get(CSRF_URL)

        xsrf_cookie = self.session.cookies.get("XSRF-TOKEN")
        if xsrf_cookie:
            self.session.headers.update({"X-XSRF-TOKEN": urllib.parse.unquote(xsrf_cookie)})

        # 2. Login
        login_payload = {
            "accountReference": self.username,
            "password": self.password,
            "mfaCode": "",
            "remember": "1"
        }
        res_login = self.session.post(LOGIN_URL, json=login_payload)
        if res_login.status_code != 200:
            raise UpdateFailed(f"Login failed: {res_login.status_code}")

        res_data = res_login.json()
        token = res_data.get("token") or res_data.get("response", {}).get("token")
        if not token:
            raise UpdateFailed("Login succeeded but no Bearer token was returned.")

        self.session.headers["Authorization"] = f"Bearer {token}"

        # 3. Fetch Telemetry Data
        res = self.session.get(DATA_URL)
        if res.status_code != 200:
            raise UpdateFailed(f"Data fetch failed: {res.status_code}")

        payload = res.json()
        data = payload.get("response", {}).get("data", {})
        if not data:
            raise UpdateFailed("Response structure invalid or missing data dictionary.")

        return data

    async def _async_update_data(self):
        """Fetch data from API using executor threads."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Flogas API: {err}") from err


class FlogasBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor class for Flogas entities."""

    def __init__(self, coordinator):
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Return device registry info."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.username)},
            "name": "Flogas LPG Tank",
            "manufacturer": "Flogas",
        }


class FlogasTankPercentageSensor(FlogasBaseSensor):
    """Sensor for remaining tank percentage."""

    _attr_name = "Tank Level"
    _attr_unique_id = "flogas_tank_level"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:gauge"

    @property
    def native_value(self):
        return self.coordinator.data.get("remainingPercentage")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {
            "last_gauge_reading": data.get("lastGaugeReading"),
            "warning_threshold": data.get("warningThreshold"),
            "order_percentage": data.get("orderPercentage"),
            "has_order": data.get("hasOrder"),
        }


class FlogasTankCapacitySensor(FlogasBaseSensor):
    """Sensor for total tank capacity."""

    _attr_name = "Tank Capacity"
    _attr_unique_id = "flogas_tank_capacity"
    _attr_native_unit_of_measurement = "L"
    _attr_icon = "mdi:fuel"

    @property
    def native_value(self):
        return self.coordinator.data.get("tankCapacity")


class FlogasDailyUsageSensor(FlogasBaseSensor):
    """Sensor for average daily usage percentage."""

    _attr_name = "Average Daily Usage"
    _attr_unique_id = "flogas_average_daily_usage"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:chart-line"

    @property
    def native_value(self):
        val = self.coordinator.data.get("averageDailyUsage")
        return round(val, 4) if val is not None else None


class FlogasLastReadingDateSensor(FlogasBaseSensor):
    """Sensor for last reading timestamp."""

    _attr_name = "Last Reading Date"
    _attr_unique_id = "flogas_last_reading_date"
    _attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self):
        return self.coordinator.data.get("lastGaugeReadingDateIso")
