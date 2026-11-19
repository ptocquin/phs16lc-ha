"""Entité de base PHS16-LC : coordinator + DeviceInfo (hub adaptateur + device par SPOT)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PORT, DOMAIN, entry_value
from .coordinator import Phs16Coordinator


def ensure_hub_device(hass: HomeAssistant, entry) -> str:
    """Crée (ou retrouve) le device hub du bus et retourne son id registry.

    Appelé dans `async_setup_entry` : les devices SPOT y font référence via
    `via_device_id` (le paramètre `via_device` de DeviceInfo est déprécié en
    HA 2026.11 et fait échouer l'ajout d'entités hors du frame de setup).
    """
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"PHS16-LC {entry_value(entry, CONF_PORT)}",
        manufacturer="Twin Development sa",
        model="Bus RS-485 PHS16-LC",
    )
    return device.id


def hub_device_info(entry_id: str, port: str) -> DeviceInfo:
    """Device hub : l'adaptateur USB-RS422 / le bus, point d'entrée de tous les SPOT.

    Mêmes identifiants que `ensure_hub_device` : un seul et même device registry.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=f"PHS16-LC {port}",
        manufacturer="Twin Development sa",
        model="Bus RS-485 PHS16-LC",
    )


def spot_device_info(hub_device_id: str, address: int) -> DeviceInfo:
    """Device d'une carte SPOT, relié au hub via `via_device_id` (id du device hub)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"spot_{address}")},
        via_device_id=hub_device_id,
        name=f"SPOT {address}",
        manufacturer="Twin Development sa",
        model="PHS16-LC",
    )


def group_device_info(entry_id: str, group_id: str, hub_device_id: str, name: str) -> DeviceInfo:
    """Device d'un groupe de luminaires, relié au hub via `via_device_id`.

    Le device est créé par HA à l'ajout de la première entité portant ce
    DeviceInfo (identifiants `(DOMAIN, "group_<id>")`) ; l'area et le label du
    groupe y sont posés par `groups.sync_group_registries`.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"group_{group_id}")},
        via_device_id=hub_device_id,
        name=name,
        manufacturer="Twin Development sa",
        model="Groupe de luminaires PHS16-LC",
    )


class Phs16Entity(CoordinatorEntity[Phs16Coordinator]):
    """Base commune : unique_id stable + device SPOT. `entity_key` distingue les plateformes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Phs16Coordinator, address: int, entity_key: str) -> None:
        super().__init__(coordinator)
        self.address = address
        self._attr_device_info = spot_device_info(coordinator.hub_device_id, address)
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


def add_group_entities_listener(
    hass,
    entry,
    coordinator: Phs16Coordinator,
    async_add_entities,
    factory: Callable[[str], object],
) -> None:
    """Crée `factory(group_id)` pour chaque groupe connu, et à chaque rechargement
    de `groups.json` (les groupes sont relus à chaque cycle de polling, D20)."""
    known: set[str] = set()

    @callback
    def _add_new_groups() -> None:
        new = []
        for group_id in coordinator.groups:
            if group_id in known:
                continue
            result = factory(group_id)
            entities = result if isinstance(result, list) else [result]
            new.extend(entities)
            known.add(group_id)
        if new:
            async_add_entities(new)

    _add_new_groups()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_groups))
