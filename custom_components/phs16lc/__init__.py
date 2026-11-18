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

from .const import (
    CONF_RECIPES_DIR,
    CONF_RX_PORT,
    DEFAULT_RECIPES_DIR,
    DOMAIN,
    GROUPS_FILENAME,
    entry_value,
    recipes_dir_for_entry,
    scenes_dir_for,
)
from .coordinator import Phs16Coordinator
from .entity import ensure_hub_device
from .phs16ctl.link import PhsLink
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

# Blueprints embarqués, copiés vers /config/blueprints/automation/phs16lc/ au démarrage :
# HA ne lit les blueprints que depuis /config/blueprints/, donc sans cette copie ils
# n'apparaîtraient pas dans Réglages → Automatisations → Créer → onglet Blueprint.
BLUEPRINTS_SRC_DIR = Path(__file__).parent / "blueprints" / "automation"

# Données embarquées (recettes, scènes, groupes) copiées vers <config>/phs16lc/ au
# premier démarrage SI ABSENTES : un dossier recipes_dir personnalisé reste géré
# manuellement, et on n'écrase jamais les fichiers modifiés par l'utilisateur.
EMBEDDED_RECIPES_DIR = Path(__file__).parent / "recipes"
EMBEDDED_SCENES_DIR = Path(__file__).parent / "scenes"
EMBEDDED_GROUPS_FILE = Path(__file__).parent / GROUPS_FILENAME

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

    await async_install_embedded_data(hass, entry)
    _warn_if_recipes_dir_missing(entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)  # idempotent (plusieurs entrées = plusieurs bus)
    await async_install_blueprints(hass)  # au cas où async_setup n'aurait pas tourné
    # Options modifiées dans l'UI -> recharge l'entrée (nouvel intervalle de polling, etc.)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_install_embedded_data(hass: HomeAssistant, entry: Phs16lcConfigEntry) -> int:
    """Copie les recettes/scènes/groups embarqués vers `<config>/phs16lc/` (si absents).

    Uniquement quand `recipes_dir` est celui par défaut : un dossier personnalisé
    reste géré manuellement. Copie « si absent » uniquement (jamais d'écrasement).
    Retourne le nombre de fichiers écrits.
    """
    if str(entry_value(entry, CONF_RECIPES_DIR)) != DEFAULT_RECIPES_DIR:
        return 0
    recipes_dir = recipes_dir_for_entry(entry)
    try:
        return await hass.async_add_executor_job(_install_embedded_data, recipes_dir)
    except OSError as exc:
        # ex. venv de dev sur Mac avec recipes_dir par défaut : /config n'existe pas
        # -> on ne fait pas échouer le setup, copie manuelle (GUIDE §5.4)
        _LOGGER.warning(
            "Copie auto des données embarquées impossible vers %s : %s — "
            "copiez-les manuellement (GUIDE §5.4)",
            recipes_dir,
            exc,
        )
        return 0


def _install_embedded_data(recipes_dir: Path) -> int:
    """Copie les *.json embarqués vers recipes_dir / <racine>/scenes / <racine>/groups.json."""
    dest_root = recipes_dir.parent
    copied = 0
    for src_dir, dest_dir in (
        (EMBEDDED_RECIPES_DIR, recipes_dir),
        (EMBEDDED_SCENES_DIR, dest_root / "scenes"),
    ):
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.glob("*.json")):
            dest = dest_dir / src.name
            if dest.exists():
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1
            _LOGGER.info("Donnée embarquée installée (fichier absent) : %s", dest)
    if EMBEDDED_GROUPS_FILE.is_file():
        dest_groups = dest_root / GROUPS_FILENAME
        if not dest_groups.exists():
            dest_groups.write_text(
                EMBEDDED_GROUPS_FILE.read_text(encoding="utf-8"), encoding="utf-8"
            )
            copied += 1
            _LOGGER.info("Donnée embarquée installée (fichier absent) : %s", dest_groups)
    return copied


def _warn_if_recipes_dir_missing(entry: Phs16lcConfigEntry) -> None:
    """Warn au setup si le dossier de recettes est introuvable (listes « Recette » vides).

    Les recettes/scènes/groups embarqués sont copiés automatiquement au premier
    démarrage dans le dossier par défaut ; ce warning ne survient plus que si le
    dossier a été supprimé ou si recipes_dir est personnalisé et vide.
    HA OS 16+ monte la config en `/homeassistant` dans les add-ons mais en
    `/config` dans le conteneur core : la copie se fait donc à
    `<config>/phs16lc/recipes` = `/homeassistant/phs16lc/recipes` depuis l'add-on SSH.
    """
    recipes_dir = recipes_dir_for_entry(entry)
    if not recipes_dir.is_dir():
        _LOGGER.warning(
            "Dossier de recettes introuvable : %s (scenes attendues dans %s). "
            "Les listes \u00ab Recette \u00bb seront vides. Copier les *.json du d\u00e9p\u00f4t "
            "(phs16ctl/recipes/, phs16ctl/scenes/) vers <config>/phs16lc/recipes et "
            "<config>/phs16lc/scenes — depuis l'add-on SSH de HA OS 16+ : "
            "/homeassistant/phs16lc/recipes et /homeassistant/phs16lc/scenes.",
            recipes_dir,
            scenes_dir_for(recipes_dir),
        )


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
