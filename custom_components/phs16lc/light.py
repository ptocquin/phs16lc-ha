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

from .const import DOMAIN, brightness_to_ma, ma_to_brightness
from .coordinator import Phs16Coordinator
from .entity import Phs16Entity
from .phs16ctl.controller import DEFAULT_CURRENT_MA, LuminaireError
from .phs16ctl.protocol import CURRENT_MIN_MA

DEFAULT_CHANNELS = 16


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Une lampe par SPOT connu, plus à chaque rescan."""
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


class SpotLight(Phs16Entity, LightEntity):
    """Lampe d'un SPOT : entité principale du device (`name=None` → « SPOT n »)."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_name = None  # l'entité porte le nom du device

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="light")

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
        return any(c >= CURRENT_MIN_MA for c in spot.currents)

    @property
    def brightness(self) -> int | None:
        spot = self._spot()
        if spot is None or not spot.online or spot.currents is None:
            return None
        return ma_to_brightness(max(spot.currents))

    async def async_turn_on(self, **kwargs: Any) -> None:
        spot = self._spot()
        if spot is None:
            return
        try:
            if ATTR_BRIGHTNESS in kwargs:
                ma = brightness_to_ma(int(kwargs[ATTR_BRIGHTNESS]))
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
