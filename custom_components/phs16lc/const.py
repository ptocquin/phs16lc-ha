"""Constantes de l'intégration PHS16-LC."""

from __future__ import annotations

from pathlib import Path

from homeassistant.const import CONF_PORT  # noqa: F401  (réexporté pour les autres modules)

from .phs16ctl.lumiatec import FAMILY_LUMIATEC, FAMILY_PHS16LC, STEP_MA, STEP_MAX
from .phs16ctl.protocol import CURRENT_MAX_MA, CURRENT_MIN_MA

DOMAIN = "phs16lc"

# Clés de configuration (en plus de CONF_PORT = "port")
# Port série de réception, montage dual (boîtier 2x USB-RS485-WE) ; vide = aucun
CONF_RX_PORT = "rx_port"
CONF_EXPECTED_SPOTS = "expected_spots"
CONF_POLL_INTERVAL = "poll_interval"
CONF_RECIPES_DIR = "recipes_dir"
# Famille de luminaires sur le bus : "phs16-lc" (défaut) ou "lumiatec"
CONF_FAMILY = "family"
DEFAULT_FAMILY = FAMILY_PHS16LC
#: Adresse du master lumiatec (0 = auto : élu par @GE OK au scan)
CONF_MASTER_ADDR = "master_addr"
DEFAULT_MASTER_ADDR = 0
#: Titre d'entrée par famille.
FAMILY_LABELS = {FAMILY_PHS16LC: "PHS16-LC", FAMILY_LUMIATEC: "lumiatec"}

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
EVENT_PROVISIONED = f"{DOMAIN}_provisioned"
EVENT_GROUP_RECIPE_APPLIED = f"{DOMAIN}_group_recipe_applied"
EVENT_LINK_LOST = f"{DOMAIN}_link_lost"
EVENT_RECONNECTED = f"{DOMAIN}_reconnected"

# Reconnexion automatique du port série (B2) : après ce nombre d'erreurs I/O
# consécutives (OSError pyserial, ex. adaptateur débranché à chaud) le port est
# déclaré perdu puis rouvert à chaque cycle de polling, avec rescan de la ligne.
LINK_ERROR_THRESHOLD = 3
RECONNECT_MIN_DELAY = 5.0  # secondes min entre deux tentatives de réouverture

# Groupes de luminaires (phase 10) : fichier groups.json à côté du dossier des recettes
GROUPS_FILENAME = "groups.json"
DEFAULT_CHANNELS = 16


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
                cand = Path(alt + s[len(prefix) :])
                if cand.exists():
                    return cand
    return p


def recipes_dir_for_entry(entry) -> Path:
    """Dossier des recettes effectif de l'entrée, résolu (voir resolve_config_path)."""
    return resolve_config_path(str(entry_value(entry, CONF_RECIPES_DIR)))


def scenes_dir_for(recipes_dir: str | Path) -> Path:
    """Dossier des scènes = dossier « scenes » à côté du dossier des recettes (résolu)."""
    return resolve_config_path(str(Path(recipes_dir).parent / "scenes"))


def groups_file_for(recipes_dir: str | Path) -> Path:
    """Fichier des groupes de luminaires = `groups.json` à côté du dossier des recettes (résolu)."""
    return resolve_config_path(str(Path(recipes_dir).parent / GROUPS_FILENAME))


# État persisté de la synchro des registres (labels/areas) : permet de ne jamais
# réécrite une valeur modifiée manuellement dans l'UI (voir groups.sync_group_registries)
SYNC_STATE_FILENAME = ".groups_sync_state.json"


def sync_state_file_for(recipes_dir: str | Path) -> Path:
    """Fichier d'état de la synchro = `.groups_sync_state.json` à côté de groups.json."""
    return resolve_config_path(str(Path(recipes_dir).parent / SYNC_STATE_FILENAME))


def entry_value(entry, key: str):
    """Valeur de configuration effective : `options` (modifié via l'UI) prioritaire sur `data`."""
    return entry.options.get(key, entry.data.get(key))


def min_on_ma(family: str = DEFAULT_FAMILY) -> int:
    """Courant minimal (mA) pour qu'un canal soit considéré allumé.

    phs16-lc : 74 mA (en dessous, le canal est éteint). lumiatec : 1 mA
    (step 0 = éteint, step 1 = 5,7 mA).
    """
    return 1 if family == FAMILY_LUMIATEC else CURRENT_MIN_MA


def brightness_to_ma(brightness: int, family: str = DEFAULT_FAMILY) -> int:
    """Luminosité HA 1..255 → courant (linéaire) ; 0 → 0 (éteint).

    phs16-lc : 74..2150 mA. lumiatec : step 1..87 x 5,7 mA, soit ~6..496 mA.
    """
    if brightness <= 0:
        return 0
    if family == FAMILY_LUMIATEC:
        step = max(1, round(STEP_MAX * brightness / 255))
        return max(1, round(step * STEP_MA))
    return round(CURRENT_MIN_MA + (CURRENT_MAX_MA - CURRENT_MIN_MA) * brightness / 255)


def ma_to_brightness(ma: int, family: str = DEFAULT_FAMILY) -> int:
    """Courant mA → luminosité HA 0..255 (inverse de brightness_to_ma).

    Un canal allumé donne au moins brightness 1.
    """
    if family == FAMILY_LUMIATEC:
        if ma < 1:
            return 0
        step = min(STEP_MAX, max(1, round(ma / STEP_MA)))
        return max(1, round(step * 255 / STEP_MAX))
    if ma < CURRENT_MIN_MA:
        return 0
    return max(1, round((ma - CURRENT_MIN_MA) * 255 / (CURRENT_MAX_MA - CURRENT_MIN_MA)))
