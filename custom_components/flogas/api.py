"""Client for the Flogas My Account API (datalayer.flogas.co.uk)."""
from __future__ import annotations

import logging
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp

from .const import API_BASE_URL, SOURCE_GAUGE, SOURCE_TELEMETRY

_LOGGER = logging.getLogger(__name__)

CSRF_URL = f"{API_BASE_URL}/sanctum/csrf-cookie"
LOGIN_URL = f"{API_BASE_URL}/portal/customer/login"
BULK_URL = f"{API_BASE_URL}/portal/bulk/data"
USAGE_OVERVIEW_URL = f"{API_BASE_URL}/portal/usage/data-overview"
USAGE_HISTORY_URL = f"{API_BASE_URL}/portal/usage/data"
SUPPLY_AGREEMENT_URL = f"{API_BASE_URL}/portal/bulk/supply-agreement"
HISTORY_DAYS = 90
CUSTOMER_URL = f"{API_BASE_URL}/portal/customer"
GAUGE_URL = f"{API_BASE_URL}/portal/bulk/gauge"

AUTH_STATUSES = (401, 403, 419)
TIMEOUT = aiohttp.ClientTimeout(total=30)


class FlogasError(Exception):
    """Base error talking to Flogas."""


class FlogasAuthError(FlogasError):
    """Credentials were rejected."""


class FlogasConnectionError(FlogasError):
    """Flogas could not be reached or returned an unexpected response."""


def _pence_to_pounds(value: Any) -> float | None:
    """Convert a pence string such as "54.00" to pounds."""
    try:
        return round(float(value) / 100, 4)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    """Parse the date formats the API uses (dd/mm/yyyy and ISO)."""
    if not value:
        return None
    text = str(value)
    for fmt, length in (("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(text[:length], fmt).date()
        except ValueError:
            continue
    _LOGGER.debug("Unrecognised date format: %s", text)
    return None


class FlogasAPI:
    """Flogas API client."""

    def __init__(
        self, session: aiohttp.ClientSession, account_reference: str, password: str
    ) -> None:
        """Initialize the API."""
        self._session = session
        self._account_reference = account_reference
        self._password = password
        self._token: str | None = None

    def _xsrf_token(self) -> str | None:
        for cookie in self._session.cookie_jar:
            if cookie.key == "XSRF-TOKEN":
                return urllib.parse.unquote(cookie.value)
        return None

    async def login(self) -> None:
        """Log in and store the bearer token. Raises on failure."""
        try:
            async with self._session.get(CSRF_URL, timeout=TIMEOUT) as response:
                if response.status != 204:
                    raise FlogasConnectionError(
                        f"Failed to get CSRF cookie: {response.status}"
                    )

            xsrf_token = self._xsrf_token()
            if not xsrf_token:
                raise FlogasConnectionError("No XSRF token found in cookies")

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-XSRF-TOKEN": xsrf_token,
            }
            data = {
                "accountReference": self._account_reference,
                "password": self._password,
            }
            async with self._session.post(
                LOGIN_URL, json=data, headers=headers, timeout=TIMEOUT
            ) as response:
                if 400 <= response.status < 500:
                    raise FlogasAuthError(f"Login rejected: {response.status}")
                if response.status != 200:
                    raise FlogasConnectionError(f"Login failed: {response.status}")
                result = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FlogasConnectionError(f"Error talking to Flogas: {err}") from err

        token = result.get("response", {}).get("token") if result.get("success") else None
        if not token:
            raise FlogasAuthError("Login was not successful")
        self._token = token
        _LOGGER.debug("Logged in to Flogas")

    async def _request(
        self,
        method: str,
        url: str,
        json: dict | None = None,
        retry: bool = True,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request, logging in again once if needed."""
        if self._token is None:
            await self.login()

        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}
        if xsrf_token := self._xsrf_token():
            headers["X-XSRF-TOKEN"] = xsrf_token

        try:
            async with self._session.request(
                method, url, json=json, params=params, headers=headers, timeout=TIMEOUT
            ) as response:
                if response.status in AUTH_STATUSES:
                    self._token = None
                    if not retry:
                        raise FlogasAuthError(f"Not authorised: {response.status}")
                    _LOGGER.debug("Session expired, logging in again")
                    return await self._request(method, url, json, False, params)
                if response.status != 200:
                    raise FlogasConnectionError(f"{url} returned {response.status}")
                result = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FlogasConnectionError(f"Error talking to Flogas: {err}") from err

        if not result.get("success"):
            raise FlogasConnectionError(f"{url} reported failure")
        return result.get("response") or {}

    async def get_all_data(self) -> dict[str, Any]:
        """Fetch telemetry, gauge and account data and merge them.

        The telemetry overview carries the live tank level for tanks with a
        telemetry unit. The bulk endpoint only holds the last manual gauge
        reading, so it is kept as the fallback for tanks without telemetry.
        """
        telemetry: dict[str, Any] = {}
        bulk: dict[str, Any] = {}
        errors: list[FlogasConnectionError] = []

        try:
            telemetry = (await self._request("GET", USAGE_OVERVIEW_URL)).get("data") or {}
        except FlogasConnectionError as err:
            _LOGGER.debug("Telemetry overview unavailable: %s", err)
            errors.append(err)

        try:
            bulk = await self._request("GET", BULK_URL)
        except FlogasConnectionError as err:
            _LOGGER.debug("Bulk data unavailable: %s", err)
            errors.append(err)

        if not telemetry and not bulk:
            raise errors[-1]

        balance = None
        try:
            customer = (await self._request("GET", CUSTOMER_URL)).get("customer") or {}
            balance = customer.get("balance")
        except FlogasConnectionError as err:
            _LOGGER.debug("Customer data unavailable: %s", err)

        supply: dict[str, Any] = {}
        try:
            supply = await self._request("GET", SUPPLY_AGREEMENT_URL)
        except FlogasConnectionError as err:
            _LOGGER.debug("Supply agreement unavailable: %s", err)
        # Prices come as pence strings ("priceUnit": "P"). The portal shows the
        # standing charge as bare pence; at ~26p it can only be per day.
        pence = (supply.get("priceUnit") or "P").upper() == "P"
        unit_price = _pence_to_pounds(supply.get("price")) if pence else None
        standing_charge = _pence_to_pounds(supply.get("standingCharge")) if pence else None

        has_telemetry = telemetry.get("remainingPercentage") is not None

        history: list[dict[str, Any]] = []
        if has_telemetry:
            today = date.today()
            try:
                usage = await self._request(
                    "GET",
                    USAGE_HISTORY_URL,
                    params={
                        # The portal sends DD/MM/YYYY; ISO dates are ignored and
                        # the API falls back to roughly the last month.
                        "from": (today - timedelta(days=HISTORY_DAYS)).strftime("%d/%m/%Y"),
                        "to": today.strftime("%d/%m/%Y"),
                    },
                )
                history = [
                    {"date": day.isoformat(), "level": item["level"]}
                    for item in usage.get("usage") or []
                    if (day := _parse_date(item.get("date"))) and item.get("level") is not None
                ]
            except FlogasConnectionError as err:
                _LOGGER.debug("Telemetry history unavailable: %s", err)
        if has_telemetry:
            source = SOURCE_TELEMETRY
            level = telemetry.get("remainingPercentage")
            reading_date = _parse_date(
                telemetry.get("lastGaugeReadingDateIso")
                or telemetry.get("lastGaugeReadingDate")
            )
            days_remaining = telemetry.get("daysRemaining")
        else:
            source = SOURCE_GAUGE
            level = bulk.get("remainingPercentage")
            reading_date = _parse_date(bulk.get("lastGaugeReadingDate"))
            days_remaining = bulk.get("daysRemaining")

        capacity = telemetry.get("tankCapacity") or bulk.get("tankCapacity")
        daily_pct = telemetry.get("averageDailyUsage")

        # Telemetry returns no days remaining, so estimate it from average use
        if days_remaining is None and level is not None and daily_pct:
            days_remaining = round(level / daily_pct)

        daily_litres = capacity * daily_pct / 100 if capacity and daily_pct is not None else None
        daily_cost = (
            round(daily_litres * unit_price + (standing_charge or 0), 2)
            if daily_litres is not None and unit_price is not None
            else None
        )

        return {
            "source": source,
            "remaining_percentage": level,
            "last_reading_date": reading_date,
            "days_remaining": days_remaining,
            "tank_capacity": capacity,
            "remaining_litres": (
                round(capacity * level / 100) if capacity and level is not None else None
            ),
            "daily_usage_percentage": daily_pct,
            "daily_usage_litres": (
                round(capacity * daily_pct / 100, 2)
                if capacity and daily_pct is not None
                else None
            ),
            "usage_this_week": telemetry.get("usageThisWeekPercentage"),
            "usage_last_week": telemetry.get("usageLastWeekPercentage"),
            "order_threshold": telemetry.get("orderPercentage"),
            "next_order_date": _parse_date(telemetry.get("nextOrder")),
            "next_delivery_date": _parse_date(telemetry.get("nextDeliveryDate")),
            "has_order": telemetry.get("hasOrder"),
            "balance": balance,
            "history": history,
            "unit_price": unit_price,
            "sales_unit": supply.get("salesUnit"),
            "standing_charge": standing_charge,
            "daily_cost": daily_cost,
            "monthly_cost": round(daily_cost * 365 / 12, 2) if daily_cost is not None else None,
            "contract_start_date": _parse_date(supply.get("contractStartDate")),
            "contract_end_date": _parse_date(supply.get("contractEndDate")),
            "contract_expired": supply.get("hasExpired"),
        }

    async def submit_gauge_reading(self, reading: int) -> dict[str, Any]:
        """Submit a tank gauge reading (0-100%) to Flogas."""
        if not 0 <= reading <= 100:
            raise ValueError("Reading must be between 0 and 100")
        response = await self._request("POST", GAUGE_URL, json={"reading": reading})
        _LOGGER.info("Submitted gauge reading: %d%%", reading)
        return response
