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
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_EXPECTED_SPOTS,
    CONF_POLL_INTERVAL,
    DEFAULT_CHANNELS,
    DOMAIN,
    EVENT_GROUP_RECIPE_APPLIED,
    EVENT_RECIPE_APPLIED,
    EVENT_SAVED,
    EVENT_SCANNED,
    EVENT_SCENE_APPLIED,
    entry_value,
    groups_file_for,
    recipes_dir_for_entry,
    scenes_dir_for,
    sync_state_file_for,
)
from .groups import GroupDef, load_groups, load_sync_state, save_sync_state, sync_group_registries
from .phs16ctl.controller import (
    DEFAULT_CURRENT_MA,
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
            update_interval=timedelta(seconds=int(entry_value(entry, CONF_POLL_INTERVAL))),
        )
        self.entry = entry
        self.link = link
        #: id registry du device hub, renseigné par `async_setup_entry` (entity.ensure_hub_device)
        self.hub_device_id: str = ""
        #: groupes de luminaires chargés depuis groups.json (rechargés à chaque polling, D20)
        self.groups: dict[str, GroupDef] = {}
        #: récap de la dernière synchro des registres (labels/areas) — exposé en diagnostics
        self.group_registry_sync: dict[str, Any] = {}
        #: état persisté de la synchro (valeurs appliquées) — anti-conflit avec l'UI
        self.sync_state: dict[str, Any] = {}
        self.sync_state_path = sync_state_file_for(recipes_dir_for_entry(entry))
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
        expected = int(entry_value(self.entry, CONF_EXPECTED_SPOTS))
        addresses = await self.async_io(_rescan, self.link, expected)
        _LOGGER.info("Scan initial PHS16-LC : %d carte(s) : %s", len(addresses), addresses)
        self.data = Phs16Data(
            link=self.link,
            spots={a: SpotState(address=a, online=True) for a in addresses},
        )
        self.sync_state = await self.async_io(load_sync_state, self.sync_state_path)
        await self._async_reload_groups()

    async def _async_reload_groups(self) -> None:
        """Recharge groups.json (executor) et resynchronise labels/areas des registres.

        La synchro n'écrase jamais une valeur modifiée manuellement dans l'UI :
        elle ne réécrit que ce qu'elle a elle-même posé (état persisté) et
        inchangé depuis. Les devices des SPOT pouvant apparaître après ce
        coordinator, on resynchronise à chaque polling (no-op si rien à changer).
        """
        path = groups_file_for(recipes_dir_for_entry(self.entry))
        groups = await self.async_io(load_groups, path)
        if groups != self.groups:
            _LOGGER.info("Groupes PHS16-LC rechargés depuis %s : %s", path, sorted(groups))
        self.groups = groups
        result = sync_group_registries(self.hass, self.entry, self.groups, self.sync_state)
        self.group_registry_sync = result.recap
        if result.dirty:
            await self.async_io(save_sync_state, self.sync_state_path, self.sync_state)

    async def _async_update_data(self) -> Phs16Data:
        await self._async_reload_groups()
        await self.async_io(_poll_spots, self.link, self.data.spots)
        return self.data

    async def async_rescan(self) -> list[int]:
        """Rescan complet (bouton/service) : découvre les nouvelles cartes, marque les absentes."""
        expected = int(entry_value(self.entry, CONF_EXPECTED_SPOTS))
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

    async def async_apply_recipe(
        self, address: int, recipe_name: str, group: str | None = None
    ) -> None:
        """Applique une recette du dossier configuré à une carte (partielle si `group`).

        Tire l'événement `phs16lc_recipe_applied` (ok/erreur). Lève en cas d'échec.
        """
        recipe_path = recipes_dir_for_entry(self.entry) / recipe_name

        def _do() -> None:
            recipe = Recipe.from_file(recipe_path)
            lum = Luminaire(address=address, link=self.link)
            lum.apply_recipe(recipe, group=group)

        try:
            await self.async_io(_do)
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            self.hass.bus.async_fire(
                EVENT_RECIPE_APPLIED,
                {
                    "address": address,
                    "recipe": recipe_name,
                    "group": group,
                    "ok": False,
                    "error": str(exc),
                },
            )
            raise
        spot = self.data.spots.get(address)
        if spot is not None and group is None:
            spot.last_recipe = recipe_name
        self.hass.bus.async_fire(
            EVENT_RECIPE_APPLIED,
            {"address": address, "recipe": recipe_name, "group": group, "ok": True},
        )
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()

    async def async_save(self, address: int) -> None:
        """Sauvegarde les courants en NVM (@WP). Tire `phs16lc_saved`. Lève LuminaireError."""
        lum = Luminaire(address=address, link=self.link)
        try:
            await self.async_io(lum.save)
        except LuminaireError as exc:
            self.hass.bus.async_fire(
                EVENT_SAVED, {"address": address, "ok": False, "error": str(exc)}
            )
            raise
        self.hass.bus.async_fire(EVENT_SAVED, {"address": address, "ok": True})
        # refresh direct (pas le debouncer) : l'état doit être à jour juste après la commande
        await self.async_refresh()

    async def async_apply_scene(self, scene_name: str, save: bool = False) -> list[CardResult]:
        """Applique un fichier de scène (dossier `scenes/` à côté de `recipes_dir`)."""
        scene_path = scenes_dir_for(recipes_dir_for_entry(self.entry)) / scene_name

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

    # ------------------------------------------------------------------
    # Groupes de luminaires (phase 10, D20/D22)
    # ------------------------------------------------------------------
    def group_addresses(self, group_id: str) -> list[int]:
        """Adresses déclarées du groupe. Lève KeyError si le groupe est inconnu."""
        group = self.groups.get(group_id)
        if group is None:
            raise KeyError(group_id)
        return list(group.addresses)

    def _member_channels(self, address: int) -> int:
        spot = self.data.spots.get(address)
        if spot is not None and spot.currents:
            return len(spot.currents)
        return DEFAULT_CHANNELS

    async def async_apply_recipe_to_group(
        self, group_id: str, recipe_name: str, group: str | None = None
    ) -> dict[int, str | None]:
        """Applique une recette à toutes les cartes du groupe (une passe série, un refresh).

        Retourne {address: erreur_ou_None} ; un membre en erreur n'interrompt pas les
        autres (comme apply_scene). Tire `phs16lc_recipe_applied` par membre + le
        récapitulatif `phs16lc_group_recipe_applied`. Lève OSError/ValueError si la
        recette est illisible, KeyError si le groupe est inconnu.
        """
        addresses = self.group_addresses(group_id)
        recipe_path = recipes_dir_for_entry(self.entry) / recipe_name

        def _do() -> dict[int, str | None]:
            recipe = Recipe.from_file(recipe_path)  # lève OSError/ValueError -> propagate
            results: dict[int, str | None] = {}
            for address in addresses:
                lum = Luminaire(
                    address=address, link=self.link, channels=self._member_channels(address)
                )
                try:
                    lum.apply_recipe(recipe, group=group)
                    results[address] = None
                except LuminaireError as exc:
                    results[address] = str(exc)
            return results

        results = await self.async_io(_do)
        for address, error in results.items():
            spot = self.data.spots.get(address)
            if error is None and group is None and spot is not None:
                spot.last_recipe = recipe_name
            self.hass.bus.async_fire(
                EVENT_RECIPE_APPLIED,
                {
                    "address": address,
                    "recipe": recipe_name,
                    "group": group,
                    "group_id": group_id,
                    "ok": error is None,
                    "error": error,
                },
            )
        self.hass.bus.async_fire(
            EVENT_GROUP_RECIPE_APPLIED,
            {
                "group": group_id,
                "recipe": recipe_name,
                "channel_group": group,
                "ok": sum(1 for e in results.values() if e is None),
                "errors": sum(1 for e in results.values() if e is not None),
                "results": {str(a): e for a, e in results.items()},
            },
        )
        await self.async_refresh()
        return results

    async def async_save_group(self, group_id: str) -> dict[int, str | None]:
        """@WP sur toutes les cartes du groupe. Retourne {address: erreur_ou_None}."""
        addresses = self.group_addresses(group_id)

        def _do() -> dict[int, str | None]:
            results: dict[int, str | None] = {}
            for address in addresses:
                lum = Luminaire(address=address, link=self.link)
                try:
                    lum.save()
                    results[address] = None
                except LuminaireError as exc:
                    results[address] = str(exc)
            return results

        results = await self.async_io(_do)
        for address, error in results.items():
            self.hass.bus.async_fire(
                EVENT_SAVED,
                {"address": address, "group_id": group_id, "ok": error is None, "error": error},
            )
        await self.async_refresh()
        return results

    async def async_set_channels_group(
        self, group_id: str, currents: list[int] | int
    ) -> dict[int, str | None]:
        """Règle les canaux de toutes les cartes du groupe.

        `currents` : liste de mA (même vecteur pour chaque carte) ou un entier mA
        (vecteur uniforme [ma] x nb_canaux de la carte). Retourne {address: erreur}.
        """
        addresses = self.group_addresses(group_id)

        def _do() -> dict[int, str | None]:
            results: dict[int, str | None] = {}
            for address in addresses:
                n = self._member_channels(address)
                vector = [currents] * n if isinstance(currents, int) else list(currents)
                lum = Luminaire(address=address, link=self.link, channels=n)
                try:
                    if len(vector) != n:
                        results[address] = f"{n} canaux attendus, {len(vector)} fournis"
                    else:
                        lum.set_channels(vector)
                        results[address] = None
                except LuminaireError as exc:
                    results[address] = str(exc)
            return results

        results = await self.async_io(_do)
        await self.async_refresh()
        return results

    async def async_set_channel_group(
        self, group_id: str, channel: int, ma: int
    ) -> dict[int, str | None]:
        """Règle un canal sur toutes les cartes du groupe (patch du vecteur courant)."""
        addresses = self.group_addresses(group_id)

        def _do() -> dict[int, str | None]:
            results: dict[int, str | None] = {}
            for address in addresses:
                spot = self.data.spots.get(address)
                base = (
                    list(spot.currents)
                    if spot is not None and spot.currents
                    else [0] * self._member_channels(address)
                )
                if not 1 <= channel <= len(base):
                    results[address] = f"canal {channel} hors limites (1..{len(base)})"
                    continue
                base[channel - 1] = ma
                lum = Luminaire(address=address, link=self.link, channels=len(base))
                try:
                    lum.set_channels(base)
                    results[address] = None
                except LuminaireError as exc:
                    results[address] = str(exc)
            return results

        results = await self.async_io(_do)
        await self.async_refresh()
        return results

    async def async_restore_group(self, group_id: str) -> dict[int, str | None]:
        """`light.turn_on` sans luminosité appliqué au groupe (D11) : chaque membre
        réapplique sa dernière recette, ou DEFAULT_CURRENT_MA si aucune."""
        addresses = self.group_addresses(group_id)
        recipes_dir = recipes_dir_for_entry(self.entry)

        def _do() -> dict[int, str | None]:
            results: dict[int, str | None] = {}
            for address in addresses:
                n = self._member_channels(address)
                lum = Luminaire(address=address, link=self.link, channels=n)
                spot = self.data.spots.get(address)
                recipe_name = spot.last_recipe if spot is not None else None
                try:
                    if recipe_name:
                        lum.apply_recipe(Recipe.from_file(recipes_dir / recipe_name))
                    else:
                        lum.set_channels([DEFAULT_CURRENT_MA] * n)
                    results[address] = None
                except (LuminaireError, OSError, ValueError, KeyError) as exc:
                    results[address] = str(exc)
            return results

        results = await self.async_io(_do)
        await self.async_refresh()
        return results
