"""Intégration Home Assistant pour les luminaires PHS16-LC (bus RS-485 full duplex).

Le cœur métier est la copie vendored de `phs16ctl` (voir `tools/sync_phs16ctl.py`) :
`protocol.py`, `link.py`, `controller.py` restent la source de vérité du projet.

Un seul propriétaire du port série : cette intégration (D7). La CLI `phs16ctl` ne
doit pas tourner en parallèle sur le même port.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import CONF_RX_PORT, DOMAIN
from .coordinator import Phs16Coordinator
from .entity import ensure_hub_device
from .phs16ctl.link import PhsLink
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

# Blueprints embarqués, copiés vers /config/blueprints/automation/phs16lc/ au démarrage :
# HA ne lit les blueprints que depuis /config/blueprints/, donc sans cette copie ils
# n'apparaîtraient pas dans Réglages → Automatisations → Créer → onglet Blueprint.
BLUEPRINTS_SRC_DIR = Path(__file__).parent / "blueprints" / "automation"

# Toutes les plateformes sont en place (phases 1-5)
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SENSOR,
]

Phs16lcConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Installe les blueprints embarqués dans /config/blueprints/automation/phs16lc/."""
    await async_install_blueprints(hass)
    return True


async def async_install_blueprints(hass: HomeAssistant) -> int:
    """Copie les blueprints embarqués (executor). Retourne le nombre de fichiers écrits."""
    dest_root = Path(hass.config.path("blueprints", "automation", DOMAIN))
    return await hass.async_add_executor_job(_install_blueprints, dest_root)


def _install_blueprints(dest_root: Path) -> int:
    """Copie chaque blueprint embarqué si absent ou modifié. Retourne le nb de fichiers écrits."""
    if not BLUEPRINTS_SRC_DIR.is_dir():
        return 0
    copied = 0
    for src in sorted(BLUEPRINTS_SRC_DIR.rglob("*.yaml")):
        dest = dest_root / src.relative_to(BLUEPRINTS_SRC_DIR)
        content = src.read_text(encoding="utf-8")
        if dest.exists() and dest.read_text(encoding="utf-8") == content:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        copied += 1
        _LOGGER.info("Blueprint installé/mis à jour : %s", dest)
    return copied


async def async_setup_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Ouvre le port série (executor), crée le coordinator, premier scan, charge les plateformes.

    `rx_port` (optionnel) : montage dual — boîtier fabricant avec deux convertisseurs
    half duplex USB-RS485-WE, un sur la paire TX (pins 1-2), un sur la paire RX
    (pins 7-8). Vide ou identique au port TX => un seul convertisseur full duplex.
    """
    port = entry.data[CONF_PORT]
    rx_port = str(entry.data.get(CONF_RX_PORT) or "").strip() or None
    try:
        link = await hass.async_add_executor_job(PhsLink, port, rx_port)
    except Exception as exc:
        # Port absent ou déjà ouvert (ex: CLI phs16ctl en parallèle) -> retry auto
        which = port if not rx_port else f"{port} (TX) / {rx_port} (RX)"
        raise ConfigEntryNotReady(f"Port série {which} indisponible : {exc}") from exc

    coordinator = Phs16Coordinator(hass, entry, link)
    coordinator.hub_device_id = ensure_hub_device(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)  # idempotent (plusieurs entrées = plusieurs bus)
    await async_install_blueprints(hass)  # au cas où async_setup n'aurait pas tourné
    # Options modifiées dans l'UI -> recharge l'entrée (nouvel intervalle de polling, etc.)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> bool:
    """Décharge les plateformes puis ferme le port série (libéré pour la CLI, par ex.)."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: Phs16Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(coordinator.link.close)
        if not hass.data[DOMAIN]:
            async_unregister_services(hass)  # plus aucune entrée : retire les services
    return unload_ok
