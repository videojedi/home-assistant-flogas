"""Sensor platform for Flogas integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    RestoreSensor,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FlogasConfigEntry, FlogasDataUpdateCoordinator
from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class FlogasSensorEntityDescription(SensorEntityDescription):
    """Describes Flogas sensor entity."""

    value_key: str
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_TYPES: tuple[FlogasSensorEntityDescription, ...] = (
    FlogasSensorEntityDescription(
        key="tank_level",
        name="Tank Level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:propane-tank",
        value_key="remaining_percentage",
        attributes_fn=lambda data: {
            "source": data.get("source"),
            "last_reading_date": data.get("last_reading_date"),
            "tank_capacity_litres": data.get("tank_capacity"),
            # Daily telemetry readings, oldest first, for history graphs
            "history": data.get("history"),
        },
    ),
    FlogasSensorEntityDescription(
        key="remaining_litres",
        name="Gas Remaining",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:propane-tank",
        value_key="remaining_litres",
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
        key="daily_usage",
        name="Daily Usage",
        native_unit_of_measurement="L/day",
        icon="mdi:fire",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="daily_usage_litres",
        attributes_fn=lambda data: {
            "percentage_per_day": data.get("daily_usage_percentage"),
        },
    ),
    FlogasSensorEntityDescription(
        key="usage_this_week",
        name="Usage This Week",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:chart-bar",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="usage_this_week",
    ),
    FlogasSensorEntityDescription(
        key="usage_last_week",
        name="Usage Last Week",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:chart-bar",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="usage_last_week",
    ),
    FlogasSensorEntityDescription(
        key="next_order_date",
        name="Next Order Date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:truck-delivery",
        value_key="next_order_date",
        attributes_fn=lambda data: {
            "order_threshold_percentage": data.get("order_threshold"),
            "has_order": data.get("has_order"),
            "next_delivery_date": data.get("next_delivery_date"),
        },
    ),
    FlogasSensorEntityDescription(
        key="unit_price",
        name="Gas Price",
        native_unit_of_measurement="GBP/L",
        icon="mdi:cash",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_key="unit_price",
        attributes_fn=lambda data: {"sales_unit": data.get("sales_unit")},
    ),
    FlogasSensorEntityDescription(
        key="standing_charge",
        name="Standing Charge",
        native_unit_of_measurement="GBP/day",
        icon="mdi:cash-clock",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_key="standing_charge",
    ),
    FlogasSensorEntityDescription(
        key="daily_cost",
        name="Estimated Daily Cost",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:cash-multiple",
        suggested_display_precision=2,
        value_key="daily_cost",
        attributes_fn=lambda data: {
            "basis": "average daily use x gas price + standing charge",
        },
    ),
    FlogasSensorEntityDescription(
        key="monthly_cost",
        name="Estimated Monthly Cost",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:cash-multiple",
        suggested_display_precision=2,
        value_key="monthly_cost",
    ),
    FlogasSensorEntityDescription(
        key="contract_end_date",
        name="Contract End Date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:file-sign",
        value_key="contract_end_date",
        attributes_fn=lambda data: {
            "contract_start_date": data.get("contract_start_date"),
            "expired": data.get("contract_expired"),
        },
    ),
    FlogasSensorEntityDescription(
        key="tank_capacity",
        name="Tank Capacity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        icon="mdi:propane-tank-outline",
        value_key="tank_capacity",
    ),
    FlogasSensorEntityDescription(
        key="last_reading_date",
        name="Last Reading Date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar",
        value_key="last_reading_date",
    ),
    FlogasSensorEntityDescription(
        key="account_balance",
        name="Account Balance",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:currency-gbp",
        value_key="balance",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlogasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flogas sensors based on a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(
                FlogasSensor(coordinator, description, entry.entry_id)
                for description in SENSOR_TYPES
            ),
            FlogasGasConsumedSensor(coordinator, entry.entry_id),
        ]
    )


def _device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Flogas Tank",
        manufacturer="Flogas",
    )


class FlogasSensor(CoordinatorEntity[FlogasDataUpdateCoordinator], SensorEntity):
    """Representation of a Flogas sensor."""

    entity_description: FlogasSensorEntityDescription
    _attr_has_entity_name = True
    # The history list changes daily and is already held by Flogas; keep it
    # out of the recorder database.
    _unrecorded_attributes = frozenset({"history"})

    def __init__(
        self,
        coordinator: FlogasDataUpdateCoordinator,
        description: FlogasSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry_id)

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if self.entity_description.attributes_fn is None or self.coordinator.data is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


# A rise of at least this many percent is a delivery, not sensor jitter.
REFILL_THRESHOLD = 5


class FlogasGasConsumedSensor(
    CoordinatorEntity[FlogasDataUpdateCoordinator], RestoreSensor
):
    """Running total of gas used, for the Energy dashboard.

    The tank only reports whole percent, so this adds 1% of the tank capacity
    each time the level falls below the lowest level seen since the last
    refill. Tracking the lowest level means jitter (86, 85, 86, 85) is only
    counted once.
    """

    _attr_has_entity_name = True
    _attr_name = "Gas Consumed"
    _attr_icon = "mdi:fire"
    _attr_device_class = SensorDeviceClass.GAS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator: FlogasDataUpdateCoordinator, entry_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_gas_consumed"
        self._attr_device_info = _device_info(entry_id)
        self._total = 0.0
        self._lowest_level: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the running total and the lowest level seen."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._total = float(last.native_value or 0)
            except (TypeError, ValueError):
                self._total = 0.0
        if (state := await self.async_get_last_state()) is not None:
            lowest = state.attributes.get("lowest_level")
            if isinstance(lowest, (int, float)):
                self._lowest_level = float(lowest)
        self._update_total()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Add any new drop in level to the total."""
        self._update_total()
        super()._handle_coordinator_update()

    def _update_total(self) -> None:
        data = self.coordinator.data or {}
        level = data.get("remaining_percentage")
        capacity = data.get("tank_capacity")
        if not isinstance(level, (int, float)) or not capacity:
            return
        if self._lowest_level is None or level >= self._lowest_level + REFILL_THRESHOLD:
            self._lowest_level = float(level)
        elif level < self._lowest_level:
            self._total += (self._lowest_level - level) * capacity / 100
            self._lowest_level = float(level)

    @property
    def native_value(self) -> float:
        """Return litres used since this sensor was created."""
        return round(self._total, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the level the next drop is measured from."""
        return {"lowest_level": self._lowest_level}
