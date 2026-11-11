"""Constantes de l'intégration PHS16-LC."""

from __future__ import annotations

from homeassistant.const import CONF_PORT  # noqa: F401  (réexporté pour les autres modules)

from .phs16ctl.protocol import CURRENT_MAX_MA, CURRENT_MIN_MA

DOMAIN = "phs16lc"

# Clés de configuration (en plus de CONF_PORT = "port")
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


def brightness_to_ma(brightness: int) -> int:
    """Luminosité HA 1..255 → courant 74..2150 mA (linéaire) ; 0 → 0 (éteint)."""
    if brightness <= 0:
        return 0
    return round(CURRENT_MIN_MA + (CURRENT_MAX_MA - CURRENT_MIN_MA) * brightness / 255)


def ma_to_brightness(ma: int) -> int:
    """Courant mA → luminosité HA 0..255 (inverse de brightness_to_ma)."""
    if ma < CURRENT_MIN_MA:
        return 0
    return round((ma - CURRENT_MIN_MA) * 255 / (CURRENT_MAX_MA - CURRENT_MIN_MA))
