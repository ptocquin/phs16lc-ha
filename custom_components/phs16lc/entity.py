"""Entité de base PHS16-LC : coordinator + DeviceInfo (hub adaptateur + device par SPOT)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Phs16Coordinator


def hub_device_info(entry_id: str, port: str) -> DeviceInfo:
    """Device hub : l'adaptateur USB-RS422 / le bus, point d'entrée de tous les SPOT."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=f"PHS16-LC {port}",
        manufacturer="Twin Development sa",
        model="Bus RS-485 PHS16-LC",
    )


def spot_device_info(entry_id: str, address: int) -> DeviceInfo:
    """Device d'une carte SPOT, relié au hub via `via_device`."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"spot_{address}")},
        via_device=(DOMAIN, entry_id),
        name=f"SPOT {address}",
        manufacturer="Twin Development sa",
        model="PHS16-LC",
    )


class Phs16Entity(CoordinatorEntity[Phs16Coordinator]):
    """Base commune : unique_id stable + device SPOT. `entity_key` distingue les plateformes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Phs16Coordinator, address: int, entity_key: str) -> None:
        super().__init__(coordinator)
        self.address = address
        self._attr_device_info = spot_device_info(coordinator.entry.entry_id, address)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_spot_{address}_{entity_key}"


def add_spot_entities_listener(
    hass,
    entry,
    coordinator: Phs16Coordinator,
    async_add_entities,
    factory: Callable[[int], Phs16Entity],
) -> None:
    """Crée `factory(address)` pour chaque SPOT connu, et à chaque rescan (listener)."""
    known: set[int] = set()

    @callback
    def _add_new_spots() -> None:
        new = []
        for address in coordinator.data.spots:
            if address in known:
                continue
            result = factory(address)
            entities = result if isinstance(result, list) else [result]
            new.extend(entities)
            known.add(address)
        if new:
            async_add_entities(new)

    _add_new_spots()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_spots))
