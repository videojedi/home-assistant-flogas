"""Constants for the Flogas integration."""

DOMAIN = "flogas"

BASE_WEB_URL = "https://myaccount.flogas.co.uk"
API_BASE_URL = "https://datalayer.flogas.co.uk"
LOGIN_URL = f"{API_BASE_URL}/portal/customer/login"
CSRF_URL = f"{API_BASE_URL}/sanctum/csrf-cookie"
DATA_URL = f"{API_BASE_URL}/portal/overview/data-bulk"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
