"""Constants for the Flogas integration."""
from datetime import timedelta

DOMAIN = "flogas"

# Configuration
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# API URLs
LOGIN_URL = "https://myaccount.flogas.co.uk/login"
API_BASE_URL = "https://datalayer.flogas.co.uk"
API_DATA_URL = f"{API_BASE_URL}/portal/bulk/data"

# Defaults
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

# User agent
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
