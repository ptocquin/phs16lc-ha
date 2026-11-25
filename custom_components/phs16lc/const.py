"""Constantes de l'intégration PHS16-LC."""

from __future__ import annotations

import json
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
EVENT_LED_CLAMPED = f"{DOMAIN}_led_clamped"  # D24 : un courant demandé a été clampé au max LED
EVENT_DIMMED = f"{DOMAIN}_dimmed"  # D23 : slider = recette dimmée à `brightness`

# Reconnexion automatique du port série (B2) : après ce nombre d'erreurs I/O
# consécutives (OSError pyserial, ex. adaptateur débranché à chaud) le port est
# déclaré perdu puis rouvert à chaque cycle de polling, avec rescan de la ligne.
LINK_ERROR_THRESHOLD = 3
RECONNECT_MIN_DELAY = 5.0  # secondes min entre deux tentatives de réouverture

# Groupes de luminaires (phase 10) : fichier groups.json à côté du dossier des recettes
GROUPS_FILENAME = "groups.json"
DEFAULT_CHANNELS = 16

# Spécifications LED du PHS16-LC (D24/D25, GUIDE §10) : courant max (mA) et type de
# LED par canal 1..16, selon la carte LED soudée (RE=1400, WH=1800, FR=1000, BL=2000).
# Surchargeable par installation via `led_spec.json` à côté de groups.json.
DEFAULT_LED_MAX_MA: list[int] = [
    1400,
    1800,
    1000,
    1400,
    1000,
    1800,
    1400,
    2000,
    1000,
    1800,
    1400,
    2000,
    1400,
    1800,
    1000,
    1400,
]
DEFAULT_LED_TYPES: list[str] = [
    "RE",
    "WH",
    "FR",
    "RE",
    "FR",
    "WH",
    "RE",
    "BL",
    "FR",
    "WH",
    "RE",
    "BL",
    "RE",
    "WH",
    "FR",
    "RE",
]
LED_SPEC_FILENAME = "led_spec.json"
#: ancien nom du fichier de spec (avant D25) — relu en repli si led_spec.json est absent
LED_MAX_FILENAME = "led_max.json"


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


def led_spec_file_for(recipes_dir: str | Path) -> Path:
    """Fichier de spec LED = `led_spec.json` à côté de groups.json (résolu)."""
    return resolve_config_path(str(Path(recipes_dir).parent / LED_SPEC_FILENAME))


def led_max_file_for(recipes_dir: str | Path) -> Path:
    """Ancien fichier de surcharge `led_max.json` (repli legacy si led_spec.json absent)."""
    return resolve_config_path(str(Path(recipes_dir).parent / LED_MAX_FILENAME))


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


# ----------------------------------------------------------------------
# Spécifications LED par canal (D24/D25 : max mA + type de LED) et dimmer (D23)
# ----------------------------------------------------------------------
def load_led_spec(
    path: str | Path, legacy_path: str | Path | None = None
) -> tuple[list[int], list[str]]:
    """Charge la spec LED par canal (D24/D25) : retourne (courants max mA, types de LED).

    Fichier JSON optionnel `led_spec.json` (à côté de groups.json) : soit une liste
    `[1400, 1800, ...]` (types = table par défaut), soit
    `{"channels": [1400, ...], "types": ["RE", "WH", ...]}`. Si `led_spec.json` est
    absent, `legacy_path` (ancien `led_max.json`) est relu en repli.
    Valeurs clampées à [0, CURRENT_MAX_MA] ; `types` aligné sur la longueur de
    `channels` (tronqué, complété par le type par défaut du canal).
    Fichier absent ou illisible → (DEFAULT_LED_MAX_MA, DEFAULT_LED_TYPES) (GUIDE §10).
    """
    data = None
    for p in (path, legacy_path):
        if p is None:
            continue
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            break
        except OSError, ValueError:
            continue
    if data is None:
        return list(DEFAULT_LED_MAX_MA), list(DEFAULT_LED_TYPES)
    raw = data.get("channels") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        channels = list(DEFAULT_LED_MAX_MA)
    else:
        try:
            channels = [max(0, min(CURRENT_MAX_MA, int(v))) for v in raw]
        except TypeError, ValueError:
            channels = list(DEFAULT_LED_MAX_MA)
    types_raw = data.get("types") if isinstance(data, dict) else None
    if (
        isinstance(types_raw, list)
        and types_raw
        and all(isinstance(t, str) and t.strip() for t in types_raw)
    ):
        types = [t.strip().upper() for t in types_raw]
    else:
        types = list(DEFAULT_LED_TYPES)
    if len(types) < len(channels):
        types = types + [
            DEFAULT_LED_TYPES[i] if i < len(DEFAULT_LED_TYPES) else "?"
            for i in range(len(types), len(channels))
        ]
    return channels, types[: len(channels)]


def _led_max_at(led_max: list[int], index: int) -> int:
    """Max LED du canal `index` (0-based) ; hors table → max driver (pas de limite connue)."""
    return led_max[index] if index < len(led_max) else CURRENT_MAX_MA


def clamp_led_vector(currents: list[int], led_max: list[int]) -> tuple[list[int], list[int]]:
    """Clamp canal par canal aux max LED (D24).

    Retourne (vecteur clampé, canaux clampés 1-based).
    """
    out: list[int] = []
    clamped: list[int] = []
    for i, c in enumerate(currents):
        m = _led_max_at(led_max, i)
        if c > m:
            clamped.append(i + 1)
            out.append(m)
        else:
            out.append(c)
    return out, clamped


def dim_vector(recipe: list[int], brightness: int, led_max: list[int]) -> list[int]:
    """Dimmer d'une recette (D23) : courbe linéaire canal par canal, de 74 mA (b=1)
    à la recette clampée LED (b=255) : `ma_i = 74 + (recette_i - 74) * b / 255`.
    Canaux à 0 dans la recette → 0 ; b=0 → tout éteint.
    """
    b = max(0, min(255, int(brightness)))
    out: list[int] = []
    for i, r in enumerate(recipe):
        if b <= 0 or r <= 0:
            out.append(0)
            continue
        r = min(r, _led_max_at(led_max, i))
        out.append(round(CURRENT_MIN_MA + (r - CURRENT_MIN_MA) * b / 255))
    return out


def brightness_from_vector(
    currents: list[int], recipe: list[int], led_max: list[int]
) -> int | None:
    """Ratio inverse du dimmer (D23) : `b` tel que `dim_vector(recipe, b) ≈ currents`.

    Canal de référence = canal de la recette clampée le plus élevé (> 74 mA).
    Retourne None si la recette n'allume aucun canal, ou si les courants lus ne
    correspondent pas à un dimming de la recette (modification externe, ex. CLI) :
    l'appelant retombe alors sur l'affichage « courant max » (D10).
    """
    ref: int | None = None
    ref_ma = 0
    for i, r in enumerate(recipe):
        r = min(r, _led_max_at(led_max, i))
        if r > CURRENT_MIN_MA and r > ref_ma:
            ref, ref_ma = i, r
    if ref is None or ref >= len(currents):
        return None
    ma = currents[ref]
    if ma <= 0:
        return 0
    b = max(1, min(255, round(255 * (ma - CURRENT_MIN_MA) / (ref_ma - CURRENT_MIN_MA))))
    # cohérence : chaque canal allumé de la recette doit matcher à ± max(12 mA, 4 %)
    for i, r in enumerate(recipe):
        if r <= 0 or i >= len(currents):
            continue
        r = min(r, _led_max_at(led_max, i))
        expected = round(CURRENT_MIN_MA + (r - CURRENT_MIN_MA) * b / 255)
        if abs(currents[i] - expected) > max(12, round(0.04 * expected)):
            return None
    return b
