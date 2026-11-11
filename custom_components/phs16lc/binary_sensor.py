"""Capteur binaire de présence de chaque carte SPOT sur le bus."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Phs16Coordinator
from .entity import Phs16Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée une entité de présence par SPOT connu, et en ajoute à chaque rescan."""
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    @callback
    def _add_new_spots() -> None:
        new = [
            SpotPresenceBinarySensor(coordinator, address)
            for address in coordinator.data.spots
            if address not in known
        ]
        for entity in new:
            known.add(entity.address)
        if new:
            async_add_entities(new)

    _add_new_spots()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_spots))


class SpotPresenceBinarySensor(Phs16Entity, BinarySensorEntity):
    """« En ligne » = la carte répond au @GI pendant le polling."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "spot_online"

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="online")

    @property
    def is_on(self) -> bool | None:
        spot = self.coordinator.data.spots.get(self.address)
        return None if spot is None else spot.online
