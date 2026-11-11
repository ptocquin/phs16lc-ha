"""Intégration Home Assistant pour les luminaires PHS16-LC (bus RS-485 full duplex).

Le cœur métier est la copie vendored de `phs16ctl` (voir `tools/sync_phs16ctl.py`) :
`protocol.py`, `link.py`, `controller.py` restent la source de vérité du projet.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Peuplé au fur et à mesure des phases (light, select, button, sensor, binary_sensor)
PLATFORMS: list[Platform] = []

Phs16lcConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Charge l'intégration pour une entrée de configuration (un port série)."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Décharge l'intégration (libère le port série via le coordinator, phase 1)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
