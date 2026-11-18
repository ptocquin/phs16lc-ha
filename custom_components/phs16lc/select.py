"""Listes déroulantes par SPOT : « Recette » (application complète) et « Groupe » (partielle).

- Recette : options = fichiers `*.json` du dossier `recipes_dir` ; sélectionner
  applique la recette en entier (`apply_recipe` sans groupe) et mémorise
  `last_recipe` (utilisé par `light.turn_on()` sans luminosité, D11).
- Groupe : options = groupes de la recette courante ; sélectionner applique
  seulement ce groupe (`apply_recipe(group=...)`, application partielle).

Chaque application tire un événement `phs16lc_recipe_applied` (logbook HA).
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, recipes_dir_for_entry
from .coordinator import Phs16Coordinator
from .entity import (
    Phs16Entity,
    add_group_entities_listener,
    add_spot_entities_listener,
    group_device_info,
)
from .phs16ctl.controller import LuminaireError, Recipe


def list_recipe_files(recipes_dir: Path) -> list[str]:
    """Noms des recettes (*.json) triés ; dossier absent ou invalide → []."""
    try:
        if not recipes_dir.is_dir():
            return []
        return sorted(p.name for p in recipes_dir.glob("*.json") if p.is_file())
    except OSError:
        return []


def recipe_groups(recipes_dir: Path, recipe_name: str | None) -> list[str]:
    """Groupes nommés d'une recette, triés ; recette absente/illisible → []."""
    if not recipe_name:
        return []
    try:
        return sorted(Recipe.from_file(recipes_dir / recipe_name).groups)
    except OSError, ValueError, KeyError:
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]
    recipes_dir = recipes_dir_for_entry(entry)
    add_spot_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda address: SpotRecipeSelect(coordinator, address, recipes_dir),
    )
    add_spot_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda address: SpotGroupSelect(coordinator, address, recipes_dir),
    )
    # Select « Recette » par groupe de luminaires (groups.json, phase 10)
    add_group_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda group_id: GroupRecipeSelect(coordinator, entry, group_id, recipes_dir),
    )


class _RecipeCacheMixin:
    """Cache des options lu en executor, rafraîchi à chaque update du coordinator."""

    _recipes_dir: Path
    _options: list[str]

    def _load_options(self) -> list[str]:
        """À surcharger : lit les options sur disque (exécuté en executor)."""
        raise NotImplementedError

    async def _async_reload_options(self) -> None:
        self._options = await self.hass.async_add_executor_job(self._load_options)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await self._async_reload_options()
        self.async_on_remove(
            self.coordinator.async_add_listener(
                lambda: self.hass.async_create_task(self._async_reload_options())
            )
        )


class SpotRecipeSelect(_RecipeCacheMixin, Phs16Entity, SelectEntity):
    """Choix de la recette appliquée en entier à la carte."""

    _attr_translation_key = "recipe"

    def __init__(self, coordinator: Phs16Coordinator, address: int, recipes_dir: Path) -> None:
        Phs16Entity.__init__(self, coordinator, address, entity_key="recipe")
        self._recipes_dir = recipes_dir
        self._options: list[str] = []

    def _load_options(self) -> list[str]:
        return list_recipe_files(self._recipes_dir)

    @property
    def options(self) -> list[str]:
        return self._options

    @property
    def current_option(self) -> str | None:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or spot.last_recipe not in self._options:
            return None
        return spot.last_recipe

    async def async_select_option(self, option: str) -> None:
        if option not in self._options:
            raise HomeAssistantError(f"Recette inconnue : {option!r}")
        try:
            # le coordinator tire l'événement phs16lc_recipe_applied (ok/erreur)
            await self.coordinator.async_apply_recipe(self.address, option)
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc
        self.async_write_ha_state()


class SpotGroupSelect(_RecipeCacheMixin, Phs16Entity, SelectEntity):
    """Application partielle : un groupe de canaux de la recette courante."""

    _attr_translation_key = "group"

    def __init__(self, coordinator: Phs16Coordinator, address: int, recipes_dir: Path) -> None:
        Phs16Entity.__init__(self, coordinator, address, entity_key="group")
        self._recipes_dir = recipes_dir
        self._options: list[str] = []

    def _load_options(self) -> list[str]:
        spot = self.coordinator.data.spots.get(self.address)
        name = spot.last_recipe if spot is not None else None
        return recipe_groups(self._recipes_dir, name)

    @property
    def options(self) -> list[str]:
        return self._options

    @property
    def current_option(self) -> str | None:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or spot.last_group not in self._options:
            return None
        return spot.last_group

    async def async_select_option(self, option: str) -> None:
        spot = self.coordinator.data.spots.get(self.address)
        if spot is None or not spot.last_recipe:
            raise HomeAssistantError(f"SPOT {self.address} : choisissez d'abord une recette.")
        if option not in self._options:
            raise HomeAssistantError(f"Groupe inconnu : {option!r}")
        try:
            # le coordinator tire l'événement phs16lc_recipe_applied (ok/erreur)
            await self.coordinator.async_apply_recipe(self.address, spot.last_recipe, group=option)
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc
        spot.last_group = option
        self.async_write_ha_state()


class GroupRecipeSelect(_RecipeCacheMixin, CoordinatorEntity[Phs16Coordinator], SelectEntity):
    """Select « Recette » d'un groupe de luminaires (phase 10, D20/D22) : la sélection
    applique la recette à **tous les membres** du groupe (une passe série)."""

    _attr_translation_key = "recipe"
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Phs16Coordinator, entry: ConfigEntry, group_id: str, recipes_dir: Path
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._group_id = group_id
        self._recipes_dir = recipes_dir
        self._options: list[str] = []
        group = coordinator.groups.get(group_id)
        name = group.name if group is not None else group_id
        self._attr_device_info = group_device_info(
            entry.entry_id, group_id, coordinator.hub_device_id, name
        )
        self._attr_unique_id = f"{entry.entry_id}_group_{group_id}_recipe"

    def _load_options(self) -> list[str]:
        return list_recipe_files(self._recipes_dir)

    @property
    def options(self) -> list[str]:
        return self._options

    @property
    def available(self) -> bool:
        return self._group_id in self.coordinator.groups and super().available

    @property
    def current_option(self) -> str | None:
        if self._group_id not in self.coordinator.groups:
            return None
        recipes = {
            spot.last_recipe
            for address in self.coordinator.group_addresses(self._group_id)
            if (spot := self.coordinator.data.spots.get(address)) is not None
        }
        if len(recipes) == 1:
            only = recipes.pop()
            if only in self._options:
                return only
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in self._options:
            raise HomeAssistantError(f"Recette inconnue : {option!r}")
        try:
            results = await self.coordinator.async_apply_recipe_to_group(self._group_id, option)
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            raise HomeAssistantError(f"Groupe {self._group_id} : {exc}") from exc
        errors = {a: e for a, e in results.items() if e}
        if errors:
            raise HomeAssistantError(
                f"Groupe {self._group_id} : {len(errors)} carte(s) en erreur : {errors}"
            )
        self.async_write_ha_state()
