"""Constants for the Flogas integration."""
from datetime import timedelta

DOMAIN = "flogas"

# Configuration
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# API - Laravel Sanctum authentication pattern
API_BASE_URL = "https://datalayer.flogas.co.uk"

# Telemetry reports roughly once a day, so there is no point polling hard
DEFAULT_SCAN_INTERVAL = timedelta(hours=3)

# Data sources
SOURCE_TELEMETRY = "telemetry"
SOURCE_GAUGE = "gauge"

SERVICE_SUBMIT_GAUGE = "submit_gauge_reading"
ATTR_READING = "reading"
