"""Intégration Home Assistant pour les luminaires PHS16-LC (bus RS-485 full duplex).

Le cœur métier est la copie vendored de `phs16ctl` (voir `tools/sync_phs16ctl.py`) :
`protocol.py`, `link.py`, `controller.py` restent la source de vérité du projet.

Un seul propriétaire du port série : cette intégration (D7). La CLI `phs16ctl` ne
doit pas tourner en parallèle sur le même port.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import Phs16Coordinator
from .phs16ctl.link import PhsLink

# Peuplé au fur et à mesure des phases (button, sensor viennent ensuite)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.LIGHT, Platform.SELECT]

Phs16lcConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Ouvre le port série (executor), crée le coordinator, premier scan, charge les plateformes."""
    port = entry.data[CONF_PORT]
    try:
        link = await hass.async_add_executor_job(PhsLink, port)
    except Exception as exc:
        # Port absent ou déjà ouvert (ex: CLI phs16ctl en parallèle) -> retry auto
        raise ConfigEntryNotReady(f"Port série {port} indisponible : {exc}") from exc

    coordinator = Phs16Coordinator(hass, entry, link)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Décharge les plateformes puis ferme le port série (libéré pour la CLI, par ex.)."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: Phs16Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(coordinator.link.close)
    return unload_ok
