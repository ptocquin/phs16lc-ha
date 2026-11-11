"""Entité de base PHS16-LC : coordinator + DeviceInfo (hub adaptateur + device par SPOT)."""

from __future__ import annotations

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
