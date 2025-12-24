"""Sensor platform for Flogas integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import FlogasDataUpdateCoordinator


@dataclass(frozen=True)
class FlogasSensorEntityDescription(SensorEntityDescription):
    """Describes Flogas sensor entity."""
    
    value_key: str = ""


SENSOR_TYPES: tuple[FlogasSensorEntityDescription, ...] = (
    FlogasSensorEntityDescription(
        key="tank_level",
        name="Tank Level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:propane-tank",
        value_key="remaining_percentage",
    ),
    FlogasSensorEntityDescription(
        key="days_remaining",
        name="Days Remaining",
        native_unit_of_measurement="days",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="days_remaining",
    ),
    FlogasSensorEntityDescription(
        key="tank_capacity",
        name="Tank Capacity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        icon="mdi:propane-tank-outline",
        value_key="tank_capacity",
    ),
    FlogasSensorEntityDescription(
        key="last_reading_date",
        name="Last Reading Date",
        icon="mdi:calendar",
        value_key="last_reading_date",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flogas sensors based on a config entry."""
    coordinator: FlogasDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FlogasSensor(coordinator, description, entry)
        for description in SENSOR_TYPES
    )


class FlogasSensor(CoordinatorEntity[FlogasDataUpdateCoordinator], SensorEntity):
    """Representation of a Flogas sensor."""

    entity_description: FlogasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FlogasDataUpdateCoordinator,
        description: FlogasSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Flogas LPG Tank",
            "manufacturer": "Flogas",
            "model": "Bulk LPG Tank",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.entity_description.key == "tank_level":
            return {
                "last_reading_date": self.coordinator.data.get("last_reading_date") if self.coordinator.data else None,
                "tank_capacity_litres": self.coordinator.data.get("tank_capacity") if self.coordinator.data else None,
            }
        return {}
