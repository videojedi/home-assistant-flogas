# Flogas Home Assistant Integration

<img src="custom_components/flogas/icon.png" alt="Flogas Logo" width="200">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A custom Home Assistant integration for monitoring your Flogas bulk LPG tank level.

## About

This integration connects to the Flogas My Account portal and retrieves your tank data via their API. It was created by reverse-engineering the Flogas web portal to discover the underlying API at `datalayer.flogas.co.uk`.

### Sensors Provided

| Sensor | Description | Unit |
|--------|-------------|------|
| **Tank Level** | Current gas level. Read from the tank's telemetry unit, falling back to the last gauge reading for tanks without one. Has a `history` attribute with daily readings for the last 90 days | % |
| **Gas Remaining** | Gas left in the tank | litres |
| **Days Remaining** | Estimated days until empty. When Flogas gives none, it's worked out from average use | days |
| **Daily Usage** | Average daily use reported by Flogas | L/day |
| **Usage This Week** / **Usage Last Week** | Tank percentage used | % |
| **Next Order Date** | When Flogas expects to deliver next | date |
| **Gas Consumed** | Running total of gas used, for the Energy dashboard (see below) | litres |
| **Gas Price** | Unit price from your supply agreement | GBP/L |
| **Standing Charge** | Standing charge from your supply agreement | GBP/day |
| **Estimated Daily Cost** / **Estimated Monthly Cost** | Average daily use × gas price + standing charge | GBP |
| **Contract End Date** | End of your supply agreement | date |
| **Tank Capacity** | Total tank capacity | litres |
| **Last Reading Date** | Date of the last telemetry or gauge reading | date |
| **Account Balance** | Current account credit/debit | GBP |

The `flogas.submit_gauge_reading` service submits a manual gauge reading for tanks without telemetry.

### Energy dashboard

**Gas Consumed** can be added as a gas source under **Settings → Dashboards → Energy**. Use **Gas Price** as the price entity.

Flogas reports the level in whole percent, so the total goes up 1% of the tank capacity at a time. It counts a drop only when the level falls below the lowest level since the last delivery, so a reading that wobbles between two values is counted once. A rise of 5% or more counts as a delivery. The total starts from zero when the sensor is first created.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu (top right) → **Custom repositories**
3. Add this repository URL: `https://github.com/videojedi/home-assistant-flogas`
4. Select category: **Integration**
5. Click **Add**
6. Find "Flogas" in HACS and click **Download**
7. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/flogas` folder from this repository
2. Copy it to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **Flogas**
4. Enter your Flogas My Account email (or account number) and password
5. The integration will create sensors for your tank

## Example Lovelace Card

```yaml
type: gauge
entity: sensor.flogas_tank_tank_level
name: LPG Tank
min: 0
max: 100
needle: true
severity:
  green: 40
  yellow: 25
  red: 10
```

## Example Automation

```yaml
alias: LPG level warning
description: ""
triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.flogas_tank_tank_level
    below: 45
conditions: []
actions:
  - action: notify.all_devices
    metadata: {}
    data:
      message: LPG Tank is at {{ states('sensor.flogas_tank_tank_level') }}%
mode: single
```

## Technical Details

- **Update Interval**: 3 hours (telemetry updates about once a day)
- **API**: REST API at `datalayer.flogas.co.uk`
  - `/portal/usage/data-overview`: live level and usage (telemetry)
  - `/portal/usage/data?from=DD/MM/YYYY&to=DD/MM/YYYY`: daily history. ISO dates are ignored and the API returns about the last month instead
  - `/portal/bulk/data`: last gauge reading (fallback)
  - `/portal/bulk/supply-agreement`: price, standing charge and contract dates
- **Authentication**: Token-based via Flogas portal login. If the password changes, Home Assistant asks for the new one (re-authentication)

## Disclaimer

This integration is not affiliated with or endorsed by Flogas. Use at your own risk.

## License

MIT License
