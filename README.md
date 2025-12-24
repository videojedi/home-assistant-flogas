# Flogas Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A custom Home Assistant integration for monitoring your Flogas bulk LPG tank level.

## About

This integration connects to the Flogas My Account portal and retrieves your tank data via their API. It was created by reverse-engineering the Flogas web portal to discover the underlying API at `datalayer.flogas.co.uk`.

### Sensors Provided

| Sensor | Description | Unit |
|--------|-------------|------|
| **Tank Level** | Current gas level | % |
| **Days Remaining** | Estimated days until empty | days |
| **Tank Capacity** | Total tank capacity | litres |
| **Last Reading Date** | Date of last gauge reading | - |
| **Account Balance** | Current account credit/debit | GBP |

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
4. Enter your Flogas My Account email and password
5. The integration will create sensors for your tank

## Example Lovelace Card

```yaml
type: gauge
entity: sensor.flogas_lpg_tank_tank_level
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
automation:
  - alias: "Low LPG Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.flogas_lpg_tank_tank_level
        below: 25
    action:
      - service: notify.mobile_app
        data:
          title: "Low LPG Level"
          message: "Tank is at {{ states('sensor.flogas_lpg_tank_tank_level') }}%"
```

## Technical Details

- **Update Interval**: 1 hour
- **API**: REST API at `datalayer.flogas.co.uk`
- **Authentication**: Token-based via Flogas portal login

## Disclaimer

This integration is not affiliated with or endorsed by Flogas. Use at your own risk.

## License

MIT License
