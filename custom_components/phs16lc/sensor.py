"""Capteurs : températures (CPU, cartes LED 1/2) et courants par SPOT + état de la ligne (hub).

Les températures ont `device_class: temperature` + `state_class: measurement` :
elles sont donc historisées automatiquement par le recorder HA (D13).
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Phs16Coordinator
from .entity import Phs16Entity, add_spot_entities_listener, hub_device_info
from .phs16ctl.controller import format_currents

TEMP_KEYS = ("cpu", "led1", "led2")  # ordre de @GT : (cpu, carte LED 1, carte LED 2)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]

    def make_spot_sensors(address: int) -> list:
        sensors = [
            SpotTemperatureSensor(coordinator, address, index, key)
            for index, key in enumerate(TEMP_KEYS)
        ]
        sensors.append(SpotCurrentsSensor(coordinator, address))
        return sensors

    add_spot_entities_listener(hass, entry, coordinator, async_add_entities, make_spot_sensors)
    async_add_entities([LineStatusSensor(coordinator, entry)])


class SpotTemperatureSensor(Phs16Entity, SensorEntity):
    """Une des 3 températures d'un SPOT (@GT), en °C, historisée."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: Phs16Coordinator, address: int, index: int, key: str) -> None:
        super().__init__(coordinator, address, entity_key=f"temp_{key}")
        self._index = index
        self._attr_translation_key = f"temp_{key}"

    @property
    def native_value(self) -> float | None:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or not spot.online or spot.temperatures is None:
            return None
        return spot.temperatures[self._index]


class SpotCurrentsSensor(Phs16Entity, SensorEntity):
    """Résumé des courants du SPOT (ex. « 800x8 + 0x8 ») + détail canal par canal en attributs."""

    _attr_icon = "mdi:flash"
    _attr_translation_key = "currents"

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="currents")

    @property
    def native_value(self) -> str | None:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or not spot.online or spot.currents is None:
            return None
        return format_currents(spot.currents)

    @property
    def extra_state_attributes(self) -> dict:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or spot.currents is None:
            return {}
        return {"channels": spot.currents}


class LineStatusSensor(CoordinatorEntity[Phs16Coordinator], SensorEntity):
    """Nombre de cartes en ligne sur le bus (hub), avec listes online/offline en attributs."""

    _attr_icon = "mdi:lan"
    _attr_translation_key = "line_status"
    _attr_has_entity_name = True

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = hub_device_info(entry.entry_id, entry.data[CONF_PORT])
        self._attr_unique_id = f"{entry.entry_id}_line_status"

    @property
    def native_value(self) -> int:
        return sum(1 for s in self.coordinator.data.spots.values() if s.online)

    @property
    def extra_state_attributes(self) -> dict:
        spots = self.coordinator.data.spots
        return {
            "total": len(spots),
            "online": sorted(a for a, s in spots.items() if s.online),
            "offline": sorted(a for a, s in spots.items() if not s.online),
        }
