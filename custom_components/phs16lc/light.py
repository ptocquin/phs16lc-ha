"""Entité light : une carte SPOT = une lampe (on/off + luminosité, mA en coulisses).

Sémantique (décisions D10/D11 du PLAN) :
- état « on » = au moins un canal ≥ 74 mA ; luminosité affichée = courant max (mA → 0..255) ;
- `turn_on(brightness=b)` = tous les canaux au même courant `brightness_to_ma(b)` ;
- `turn_on()` sans luminosité = réapplique la dernière recette de la carte si elle
  existe, sinon `DEFAULT_CURRENT_MA` (500 mA) sur tous les canaux ;
- `turn_off()` = tous les canaux à 0.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_CHANNELS, DOMAIN, brightness_to_ma, ma_to_brightness, min_on_ma
from .coordinator import Phs16Coordinator
from .entity import Phs16Entity, add_group_entities_listener, group_device_info
from .phs16ctl.controller import DEFAULT_CURRENT_MA, LuminaireError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Une lampe par SPOT connu, plus à chaque rescan ; une lampe par groupe (groups.json)."""
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    @callback
    def _add_new_spots() -> None:
        new = [
            SpotLight(coordinator, address)
            for address in coordinator.data.spots
            if address not in known
        ]
        for entity in new:
            known.add(entity.address)
        if new:
            async_add_entities(new)

    _add_new_spots()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_spots))

    add_group_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda group_id: GroupLight(coordinator, entry, group_id),
    )


class SpotLight(Phs16Entity, LightEntity):
    """Lampe d'un SPOT : entité principale du device (`name=None` → « SPOT n »)."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_name = None  # l'entité porte le nom du device

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="light")
        self._family = coordinator.family  # mapping luminosité et seuil « on » par famille

    def _spot(self):
        return self.coordinator.data.spots.get(self.address)

    def _channels(self) -> int:
        spot = self._spot()
        return len(spot.currents) if spot is not None and spot.currents else DEFAULT_CHANNELS

    @property
    def is_on(self) -> bool | None:
        spot = self._spot()
        if spot is None:
            return None
        if not spot.online:
            return False
        if spot.currents is None:
            return None
        return any(c >= min_on_ma(self._family) for c in spot.currents)

    @property
    def brightness(self) -> int | None:
        spot = self._spot()
        if spot is None or not spot.online or spot.currents is None:
            return None
        return ma_to_brightness(max(spot.currents), self._family)

    async def async_turn_on(self, **kwargs: Any) -> None:
        spot = self._spot()
        if spot is None:
            return
        try:
            if ATTR_BRIGHTNESS in kwargs:
                ma = brightness_to_ma(int(kwargs[ATTR_BRIGHTNESS]), self._family)
                await self.coordinator.async_set_channels(self.address, [ma] * self._channels())
            elif spot.last_recipe:
                await self.coordinator.async_apply_recipe(self.address, spot.last_recipe)
            else:
                await self.coordinator.async_set_channels(
                    self.address, [DEFAULT_CURRENT_MA] * self._channels()
                )
        except LuminaireError as exc:
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_set_channels(self.address, [0] * self._channels())
        except LuminaireError as exc:
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc


class GroupLight(CoordinatorEntity[Phs16Coordinator], LightEntity):
    """Lampe d'un groupe de luminaires (phase 10) : on/off + luminosité sur tous les membres.

    Entité principale du device « Groupe <name> » (`name=None`). `turn_on` sans
    luminosité réapplique la dernière recette de chaque membre (D11), sinon 500 mA.
    """

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_name = None  # l'entité porte le nom du device groupe

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        group = coordinator.groups.get(group_id)
        name = group.name if group is not None else group_id
        self._attr_device_info = group_device_info(
            entry.entry_id, group_id, coordinator.hub_device_id, name
        )
        self._attr_unique_id = f"{entry.entry_id}_group_{group_id}_light"

    def _spots(self) -> list:
        if self._group_id not in self.coordinator.groups:
            return []
        return [
            spot
            for address in self.coordinator.group_addresses(self._group_id)
            if (spot := self.coordinator.data.spots.get(address)) is not None
        ]

    @property
    def available(self) -> bool:
        return self._group_id in self.coordinator.groups and super().available

    @property
    def is_on(self) -> bool | None:
        spots = self._spots()
        if not spots:
            return None
        threshold = min_on_ma(self.coordinator.family)
        return any(
            s.online and s.currents and any(c >= threshold for c in s.currents) for s in spots
        )

    @property
    def brightness(self) -> int | None:
        spots = [s for s in self._spots() if s.online and s.currents]
        if not spots:
            return None
        return ma_to_brightness(max(max(s.currents) for s in spots), self.coordinator.family)

    async def _run_group(self, coro) -> None:
        try:
            results = await coro
        except KeyError as exc:
            raise HomeAssistantError(f"Groupe {self._group_id} inconnu (groups.json)") from exc
        errors = {a: e for a, e in results.items() if e}
        if errors:
            raise HomeAssistantError(
                f"Groupe {self._group_id} : {len(errors)} carte(s) en erreur : {errors}"
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            ma = brightness_to_ma(int(kwargs[ATTR_BRIGHTNESS]), self.coordinator.family)
            await self._run_group(self.coordinator.async_set_channels_group(self._group_id, ma))
        else:
            # D11 appliqué au groupe : dernière recette de chaque membre, sinon 500 mA
            await self._run_group(self.coordinator.async_restore_group(self._group_id))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run_group(self.coordinator.async_set_channels_group(self._group_id, 0))
