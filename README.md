# Flogas Home Assistant Integration

A custom Home Assistant integration that monitors your Flogas LPG tank level by connecting to the Flogas My Account portal.

## Features

- Automatically polls the Flogas API every hour
- Displays tank level as a percentage
- Shows days remaining estimate
- Tank capacity information
- Last reading date
- Easy configuration through the Home Assistant UI
- HACS compatible

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS:
   - Click on HACS in the sidebar
   - Click on "Integrations"
   - Click the three dots in the top right
   - Select "Custom repositories"
   - Enter the repository URL and select "Integration" as the category

2. Install the "Flogas" integration through HACS
3. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/flogas` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **Flogas**
4. Enter your credentials:
   - **Email**: Your Flogas account email
   - **Password**: Your Flogas account password

## Sensors Created

| Sensor | Description | Unit |
|--------|-------------|------|
| Tank Level | Current gas level percentage | % |
| Days Remaining | Estimated days until empty | days |
| Tank Capacity | Total tank capacity | litres |
| Last Reading Date | Date of last gauge reading | - |

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
          message: >
            Your LPG tank is at {{ states('sensor.flogas_lpg_tank_tank_level') }}%
            with {{ states('sensor.flogas_lpg_tank_days_remaining') }} days remaining
```

## Example Lovelace Card

```yaml
type: gauge
entity: sensor.flogas_lpg_tank_tank_level
min: 0
max: 100
needle: true
severity:
  green: 40
  yellow: 25
  red: 10
```

## Technical Details

- **Update Interval**: 1 hour
- **API Method**: REST API (datalayer.flogas.co.uk)
- **Authentication**: Token-based via Flogas portal login

## Support

For issues and feature requests, please open an issue on GitHub.

## Disclaimer

This integration is not affiliated with or endorsed by Flogas. Use at your own risk.

## License

MIT License
