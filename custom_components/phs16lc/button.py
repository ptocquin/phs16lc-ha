"""Boutons : « Sauvegarder NVM » par SPOT, « Scanner la ligne » et une scène par fichier (hub)."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, entry_value, recipes_dir_for_entry, scenes_dir_for
from .coordinator import Phs16Coordinator
from .entity import (
    Phs16Entity,
    add_group_entities_listener,
    add_spot_entities_listener,
    group_device_info,
    hub_device_info,
)
from .phs16ctl.controller import LuminaireError


def list_scene_files(scenes_dir: Path) -> list[str]:
    """Noms des fichiers scène (*.json) triés ; dossier absent → []."""
    try:
        if not scenes_dir.is_dir():
            return []
        return sorted(p.name for p in scenes_dir.glob("*.json") if p.is_file())
    except OSError:
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]
    scenes_dir = scenes_dir_for(recipes_dir_for_entry(entry))

    # Bouton par SPOT : sauvegarder NVM
    add_spot_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda address: SpotSaveButton(coordinator, address),
    )

    # Bouton « Sauvegarder NVM » par groupe de luminaires (groups.json, phase 10)
    add_group_entities_listener(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda group_id: GroupSaveButton(coordinator, entry, group_id),
    )

    # Boutons hub : scan + re-provisionnement + un bouton par fichier de scène
    async_add_entities([ScanButton(coordinator, entry), ProvisionButton(coordinator, entry)])
    known_scenes: set[str] = set()

    async def _async_add_scene_buttons() -> None:
        scenes = await hass.async_add_executor_job(list_scene_files, scenes_dir)
        new = [SceneButton(coordinator, entry, name) for name in scenes if name not in known_scenes]
        known_scenes.update(scenes)
        if new:
            async_add_entities(new)

    await _async_add_scene_buttons()
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: hass.async_create_task(_async_add_scene_buttons()))
    )


class HubButton(CoordinatorEntity[Phs16Coordinator], ButtonEntity):
    """Bouton rattaché au device hub (adaptateur/bus), pas à un SPOT."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Phs16Coordinator,
        entry: ConfigEntry,
        entity_key: str,
        translation_key: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = hub_device_info(entry.entry_id, str(entry_value(entry, CONF_PORT)))
        self._attr_unique_id = f"{entry.entry_id}_{entity_key}"
        if translation_key is not None:
            self._attr_translation_key = translation_key
        if name is not None:
            self._attr_name = name


class ScanButton(HubButton):
    """Rescan complet de la ligne (découverte des cartes, présences mises à jour)."""

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, entity_key="scan", translation_key="scan")

    async def async_press(self) -> None:
        # le coordinator tire l'événement phs16lc_scan
        await self.coordinator.async_rescan()


class ProvisionButton(HubButton):
    """Re-provisionnement manuel de la ligne (@UNP + @DI/@PRG, README §5.2).

    Action d'installation délibérément manuelle : réinitialise TOUTES les
    adresses du bus puis les réalloue 1..N par proximité au PC. Ne JAMAIS
    déclenché par le polling.
    """

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, entity_key="provision", translation_key="provision")

    async def async_press(self) -> None:
        try:
            # le coordinator tire l'événement phs16lc_provisioned puis rescanne
            await self.coordinator.async_provision_line()
        except (LuminaireError, OSError) as exc:
            raise HomeAssistantError(f"Re-provisionnement de la ligne : {exc}") from exc


class SceneButton(HubButton):
    """Applique un fichier de scène à plusieurs cartes (bouton nommé d'après le fichier)."""

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry, scene_name: str) -> None:
        stem = Path(scene_name).stem
        super().__init__(coordinator, entry, entity_key=f"scene_{stem}", name=stem)
        self._scene_name = scene_name

    async def async_press(self) -> None:
        try:
            # le coordinator tire l'événement phs16lc_scene_applied
            await self.coordinator.async_apply_scene(self._scene_name)
        except (OSError, ValueError, KeyError, LuminaireError) as exc:
            raise HomeAssistantError(f"Scène {self._scene_name!r} illisible : {exc}") from exc


class SpotSaveButton(Phs16Entity, ButtonEntity):
    """« Sauvegarder NVM » : rend les courants actuels de la carte permanents (@WP)."""

    _attr_translation_key = "save_nvm"

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="save")

    async def async_press(self) -> None:
        try:
            # le coordinator tire l'événement phs16lc_saved (ok/erreur)
            await self.coordinator.async_save(self.address)
        except LuminaireError as exc:
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc


class GroupSaveButton(CoordinatorEntity[Phs16Coordinator], ButtonEntity):
    """« Sauvegarder NVM » d'un groupe (phase 10) : @WP sur tous les membres."""

    _attr_translation_key = "save_nvm"
    _attr_has_entity_name = True

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        group = coordinator.groups.get(group_id)
        name = group.name if group is not None else group_id
        self._attr_device_info = group_device_info(
            entry.entry_id, group_id, coordinator.hub_device_id, name
        )
        self._attr_unique_id = f"{entry.entry_id}_group_{group_id}_save"

    @property
    def available(self) -> bool:
        return self._group_id in self.coordinator.groups and super().available

    async def async_press(self) -> None:
        try:
            results = await self.coordinator.async_save_group(self._group_id)
        except KeyError as exc:
            raise HomeAssistantError(f"Groupe {self._group_id} inconnu (groups.json)") from exc
        errors = {a: e for a, e in results.items() if e}
        if errors:
            raise HomeAssistantError(
                f"Groupe {self._group_id} : {len(errors)} carte(s) en erreur : {errors}"
            )
