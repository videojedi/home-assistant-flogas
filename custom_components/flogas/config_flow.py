"""Config flow for Flogas integration."""
import logging
import urllib.parse
import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    BASE_WEB_URL,
    API_BASE_URL,
    LOGIN_URL,
    CSRF_URL,
    CONF_USERNAME,
    CONF_PASSWORD,
)

_LOGGER = logging.getLogger(__name__)


def validate_input(username, password):
    """Validate user credentials against the new Flogas API."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": BASE_WEB_URL,
        "Referer": f"{BASE_WEB_URL}/",
        "Content-Type": "application/json",
    })

    # CSRF Handshake
    session.get(BASE_WEB_URL)
    session.get(CSRF_URL)

    xsrf_cookie = session.cookies.get("XSRF-TOKEN")
    if xsrf_cookie:
        session.headers.update({"X-XSRF-TOKEN": urllib.parse.unquote(xsrf_cookie)})

    # Login payload
    payload = {
        "accountReference": username,
        "password": password,
        "mfaCode": "",
        "remember": "1"
    }

    res = session.post(LOGIN_URL, json=payload)
    if res.status_code != 200:
        raise Exception(f"Invalid auth (HTTP {res.status_code})")

    res_data = res.json()
    token = res_data.get("token") or res_data.get("response", {}).get("token")
    if not token:
        raise Exception("Login succeeded but no token was returned.")

    return True


class FlogasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flogas."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    validate_input,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except Exception as err:
                _LOGGER.error("Failed to authenticate with Flogas API: %s", err)
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Flogas ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )
