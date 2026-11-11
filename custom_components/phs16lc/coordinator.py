"""Coordinator PHS16-LC : propriétaire du lien série et du polling périodique.

Le protocole PHS16-LC est maître/esclave (pas de push) : l'état réel des cartes
est relu par polling (`@GI` présence, `@GP` courants, `@GT` températures).

Tout l'I/O série est bloquant (pyserial) : il est exécuté en executor via
`async_io()`, sérialisé par un `asyncio.Lock` — un seul thread à la fois touche
au port `/dev/ttyUSBx` (le port ne s'ouvre qu'une fois, voir D7).
"""

from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_EXPECTED_SPOTS,
    CONF_POLL_INTERVAL,
    CONF_RECIPES_DIR,
    DOMAIN,
    EVENT_RECIPE_APPLIED,
    EVENT_SAVED,
    EVENT_SCANNED,
    EVENT_SCENE_APPLIED,
    scenes_dir_for,
)
from .phs16ctl.controller import (
    CardResult,
    Luminaire,
    LuminaireError,
    Recipe,
    Scene,
    apply_scene,
    scan_line,
)
from .phs16ctl.link import T_GI, PhsLink

_LOGGER = logging.getLogger(__name__)


@dataclass
class SpotState:
    """État connu d'une carte SPOT, rafraîchi à chaque polling."""

    address: int
    online: bool = False
    currents: list[int] | None = None  # @GP (mA par canal)
    temperatures: tuple[float, float, float] | None = None  # @GT (cpu, led1, led2)
    last_recipe: str | None = None  # dernière recette appliquée en entier (D11)
    last_group: str | None = None  # dernier groupe appliqué en partiel (select « Groupe »)


@dataclass
class Phs16Data:
    link: PhsLink
    spots: dict[int, SpotState] = field(default_factory=dict)


def _poll_spots(link: PhsLink, spots: dict[int, SpotState]) -> None:
    """Batch de polling, exécuté en un seul job executor (un seul thread sur le port)."""
    for spot in spots.values():
        spot.online = link.send("GI", spot.address, timeout=T_GI) is not None
        if not spot.online:
            spot.currents = None
            spot.temperatures = None
            continue
        lum = Luminaire(address=spot.address, link=link)
        try:
            spot.currents = lum.read_currents()
        except LuminaireError:
            spot.currents = None
        try:
            spot.temperatures = lum.read_temperatures()
        except LuminaireError:
            spot.temperatures = None


def _rescan(link: PhsLink, expected: int) -> list[int]:
    """Scan complet de la ligne (exécuté en executor)."""
    return scan_line(link, expected=expected)


class Phs16Coordinator(DataUpdateCoordinator[Phs16Data]):
    """Polling périodique de la ligne PHS16-LC."""

    def __init__(self, hass: HomeAssistant, entry, link: PhsLink) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=int(entry.data[CONF_POLL_INTERVAL])),
        )
        self.entry = entry
        self.link = link
        self._io_lock = asyncio.Lock()

    async def async_io(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Exécute `func(*args)` en executor, sérialisé (port série unique)."""
        async with self._io_lock:
            return await self.hass.async_add_executor_job(functools.partial(func, *args, **kwargs))

    async def _async_setup(self) -> None:
        """Scan initial de la ligne à la création du coordinator.

        Contrat HA 2026.11 : `_async_setup` ne retourne rien, il renseigne
        `self.data` lui-même (ensuite `_async_update_data` est appelé).
        """
        expected = int(self.entry.data[CONF_EXPECTED_SPOTS])
        addresses = await self.async_io(_rescan, self.link, expected)
        _LOGGER.info("Scan initial PHS16-LC : %d carte(s) : %s", len(addresses), addresses)
        self.data = Phs16Data(
            link=self.link,
            spots={a: SpotState(address=a, online=True) for a in addresses},
        )

    async def _async_update_data(self) -> Phs16Data:
        await self.async_io(_poll_spots, self.link, self.data.spots)
        return self.data

    async def async_rescan(self) -> list[int]:
        """Rescan complet (bouton/service) : découvre les nouvelles cartes, marque les absentes."""
        expected = int(self.entry.data[CONF_EXPECTED_SPOTS])
        addresses = await self.async_io(_rescan, self.link, expected)
        for a in addresses:
            self.data.spots.setdefault(a, SpotState(address=a, online=True))
        for spot in self.data.spots.values():
            if spot.address not in addresses:
                spot.online = False
        _LOGGER.info("Rescan PHS16-LC : %d carte(s) : %s", len(addresses), addresses)
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()
        self.hass.bus.async_fire(EVENT_SCANNED, {"addresses": addresses, "count": len(addresses)})
        return addresses

    # ------------------------------------------------------------------
    # Commandes (phases 2+ : light, select, button, services)
    # ------------------------------------------------------------------
    async def async_set_channels(self, address: int, currents: list[int]) -> None:
        """Règle chaque canal d'une carte (@SP). Lève LuminaireError si la carte ne répond pas."""
        lum = Luminaire(address=address, link=self.link, channels=len(currents))
        await self.async_io(lum.set_channels, currents)
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()

    async def async_apply_recipe(self, address: int, recipe_name: str, group: str | None = None) -> None:
        """Applique une recette du dossier configuré à une carte (partielle si `group`).

        Tire l'événement `phs16lc_recipe_applied` (ok/erreur). Lève en cas d'échec.
        """
        recipe_path = Path(str(self.entry.data[CONF_RECIPES_DIR])) / recipe_name

        def _do() -> None:
            recipe = Recipe.from_file(recipe_path)
            lum = Luminaire(address=address, link=self.link)
            lum.apply_recipe(recipe, group=group)

        try:
            await self.async_io(_do)
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            self.hass.bus.async_fire(
                EVENT_RECIPE_APPLIED,
                {"address": address, "recipe": recipe_name, "group": group, "ok": False, "error": str(exc)},
            )
            raise
        spot = self.data.spots.get(address)
        if spot is not None and group is None:
            spot.last_recipe = recipe_name
        self.hass.bus.async_fire(
            EVENT_RECIPE_APPLIED, {"address": address, "recipe": recipe_name, "group": group, "ok": True}
        )
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()

    async def async_save(self, address: int) -> None:
        """Sauvegarde les courants en NVM (@WP). Tire `phs16lc_saved`. Lève LuminaireError."""
        lum = Luminaire(address=address, link=self.link)
        try:
            await self.async_io(lum.save)
        except LuminaireError as exc:
            self.hass.bus.async_fire(EVENT_SAVED, {"address": address, "ok": False, "error": str(exc)})
            raise
        self.hass.bus.async_fire(EVENT_SAVED, {"address": address, "ok": True})
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()

    async def async_apply_scene(self, scene_name: str, save: bool = False) -> list[CardResult]:
        """Applique un fichier de scène (dossier `scenes/` à côté de `recipes_dir`)."""
        scene_path = scenes_dir_for(str(self.entry.data[CONF_RECIPES_DIR])) / scene_name

        def _do() -> tuple[Scene, list[CardResult]]:
            scene = Scene.from_file(scene_path)
            results = apply_scene(self.link, scene, scene_path, save=save)
            return scene, results

        scene, results = await self.async_io(_do)
        for target in scene.targets:
            if target.group is None:
                for address in target.addresses:
                    spot = self.data.spots.get(address)
                    if spot is not None:
                        spot.last_recipe = target.recipe_ref
        self.hass.bus.async_fire(
            EVENT_SCENE_APPLIED,
            {
                "scene": scene_name,
                "ok": sum(1 for r in results if r.ok),
                "errors": sum(1 for r in results if not r.ok),
                "results": [asdict(r) for r in results],
            },
        )
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()
        return results
