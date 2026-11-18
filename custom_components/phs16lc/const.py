"""Constantes de l'intégration PHS16-LC."""

from __future__ import annotations

from pathlib import Path

from homeassistant.const import CONF_PORT  # noqa: F401  (réexporté pour les autres modules)

from .phs16ctl.protocol import CURRENT_MAX_MA, CURRENT_MIN_MA

DOMAIN = "phs16lc"

# Clés de configuration (en plus de CONF_PORT = "port")
# Port série de réception, montage dual (boîtier 2x USB-RS485-WE) ; vide = aucun
CONF_RX_PORT = "rx_port"
CONF_EXPECTED_SPOTS = "expected_spots"
CONF_POLL_INTERVAL = "poll_interval"
CONF_RECIPES_DIR = "recipes_dir"

DEFAULT_POLL_INTERVAL = 10
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 60
DEFAULT_RECIPES_DIR = "/config/phs16lc/recipes"
DEFAULT_SCENES_DIR = "/config/phs16lc/scenes"

# Événements HA (visibles dans le logbook)
EVENT_RECIPE_APPLIED = f"{DOMAIN}_recipe_applied"
EVENT_SCENE_APPLIED = f"{DOMAIN}_scene_applied"
EVENT_SAVED = f"{DOMAIN}_saved"
EVENT_SCANNED = f"{DOMAIN}_scan"


# HA OS 16+ monte la config en `/homeassistant` dans les add-ons, mais le
# conteneur core la voit (encore) en `/config` — d'où la résolution croisée.
_CONFIG_ROOTS = ("/config", "/homeassistant")


def resolve_config_path(path: str, *, roots: tuple[str, ...] = _CONFIG_ROOTS) -> Path:
    """Résout un chemin absolu de la config HA.

    Si le chemin n'existe pas et commence par l'une des racines connues
    (`/config`, `/homeassistant`), on essaie l'autre racine : la config est
    montée sous des noms différents selon le conteneur (core vs add-on HA OS 16+).
    Chemin relatif ou inexistant partout → retourné tel quel.
    """
    p = Path(path)
    if p.exists() or not p.is_absolute():
        return p
    s = str(p)
    for prefix in roots:
        if s.startswith(prefix + "/"):
            for alt in roots:
                if alt == prefix:
                    continue
                cand = Path(alt + s[len(prefix):])
                if cand.exists():
                    return cand
    return p


def recipes_dir_for_entry(entry) -> Path:
    """Dossier des recettes effectif de l'entrée, résolu (voir resolve_config_path)."""
    return resolve_config_path(str(entry_value(entry, CONF_RECIPES_DIR)))


def scenes_dir_for(recipes_dir: str | Path) -> Path:
    """Dossier des scènes = dossier « scenes » à côté du dossier des recettes (résolu)."""
    return resolve_config_path(str(Path(recipes_dir).parent / "scenes"))


def entry_value(entry, key: str):
    """Valeur de configuration effective : `options` (modifié via l'UI) prioritaire sur `data`."""
    return entry.options.get(key, entry.data.get(key))


def brightness_to_ma(brightness: int) -> int:
    """Luminosité HA 1..255 → courant 74..2150 mA (linéaire) ; 0 → 0 (éteint)."""
    if brightness <= 0:
        return 0
    return round(CURRENT_MIN_MA + (CURRENT_MAX_MA - CURRENT_MIN_MA) * brightness / 255)


def ma_to_brightness(ma: int) -> int:
    """Courant mA → luminosité HA 0..255 (inverse de brightness_to_ma).

    Un canal allumé (≥ 74 mA) donne au moins brightness 1, même à 74 mA.
    """
    if ma < CURRENT_MIN_MA:
        return 0
    return max(1, round((ma - CURRENT_MIN_MA) * 255 / (CURRENT_MAX_MA - CURRENT_MIN_MA)))
