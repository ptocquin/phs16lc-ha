"""Boutons : « Sauvegarder NVM » par SPOT, « Scanner la ligne » et une scène par fichier (hub)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_RECIPES_DIR,
    DOMAIN,
    EVENT_SAVED,
    EVENT_SCANNED,
    EVENT_SCENE_APPLIED,
    scenes_dir_for,
)
from .coordinator import Phs16Coordinator
from .entity import Phs16Entity, add_spot_entities_listener, hub_device_info
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
    scenes_dir = scenes_dir_for(str(entry.data[CONF_RECIPES_DIR]))

    # Bouton par SPOT : sauvegarder NVM
    add_spot_entities_listener(
        hass, entry, coordinator, async_add_entities,
        lambda address: SpotSaveButton(coordinator, address),
    )

    # Boutons hub : scan + un bouton par fichier de scène
    async_add_entities([ScanButton(coordinator, entry)])
    known_scenes: set[str] = set()

    async def _async_add_scene_buttons() -> None:
        scenes = await hass.async_add_executor_job(list_scene_files, scenes_dir)
        new = [
            SceneButton(coordinator, entry, name)
            for name in scenes
            if name not in known_scenes
        ]
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
        self._attr_device_info = hub_device_info(entry.entry_id, entry.data[CONF_PORT])
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
        found = await self.coordinator.async_rescan()
        self.hass.bus.async_fire(EVENT_SCANNED, {"addresses": found, "count": len(found)})


class SceneButton(HubButton):
    """Applique un fichier de scène à plusieurs cartes (bouton nommé d'après le fichier)."""

    def __init__(self, coordinator: Phs16Coordinator, entry: ConfigEntry, scene_name: str) -> None:
        stem = Path(scene_name).stem
        super().__init__(coordinator, entry, entity_key=f"scene_{stem}", name=stem)
        self._scene_name = scene_name

    async def async_press(self) -> None:
        try:
            results = await self.coordinator.async_apply_scene(self._scene_name)
        except (OSError, ValueError, KeyError, LuminaireError) as exc:
            raise HomeAssistantError(f"Scène {self._scene_name!r} illisible : {exc}") from exc
        self.hass.bus.async_fire(
            EVENT_SCENE_APPLIED,
            {
                "scene": self._scene_name,
                "ok": sum(1 for r in results if r.ok),
                "errors": sum(1 for r in results if not r.ok),
                "results": [asdict(r) for r in results],
            },
        )


class SpotSaveButton(Phs16Entity, ButtonEntity):
    """« Sauvegarder NVM » : rend les courants actuels de la carte permanents (@WP)."""

    _attr_translation_key = "save_nvm"

    def __init__(self, coordinator: Phs16Coordinator, address: int) -> None:
        super().__init__(coordinator, address, entity_key="save")

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_save(self.address)
        except LuminaireError as exc:
            self.hass.bus.async_fire(
                EVENT_SAVED, {"address": self.address, "ok": False, "error": str(exc)}
            )
            raise HomeAssistantError(f"SPOT {self.address} : {exc}") from exc
        self.hass.bus.async_fire(EVENT_SAVED, {"address": self.address, "ok": True})
