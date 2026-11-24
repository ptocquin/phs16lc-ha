"""Tests D23/D24 : table LED max, clamp systématique, dimmer de recette.

- fonctions pures de `const.py` : `load_led_max`, `clamp_led_vector`, `dim_vector`,
  `brightness_from_vector` ;
- intégration : surcharge `led_max.json`, clamp au niveau du lien (toute trame @SP,
  y compris les services set_channels/set_channel), événement `phs16lc_led_clamped`.
"""

from __future__ import annotations

import json

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState

from custom_components.phs16lc.const import (
    DEFAULT_LED_MAX_MA,
    DOMAIN,
    EVENT_LED_CLAMPED,
    brightness_from_vector,
    clamp_led_vector,
    dim_vector,
    led_max_file_for,
    load_led_max,
)

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


# ----------------------------------------------------------------------
# Fonctions pures
# ----------------------------------------------------------------------
def test_load_led_max_default_when_missing(tmp_path) -> None:
    assert load_led_max(tmp_path / "led_max.json") == DEFAULT_LED_MAX_MA


def test_load_led_max_list_and_channels_forms(tmp_path) -> None:
    p = tmp_path / "led_max.json"
    p.write_text(json.dumps([1000] * 16), encoding="utf-8")
    assert load_led_max(p) == [1000] * 16
    p.write_text(json.dumps({"channels": [500, 600]}), encoding="utf-8")
    assert load_led_max(p) == [500, 600]


def test_load_led_max_invalid_falls_back_to_default(tmp_path) -> None:
    p = tmp_path / "led_max.json"
    p.write_text("{ pas du json", encoding="utf-8")
    assert load_led_max(p) == DEFAULT_LED_MAX_MA
    p.write_text(json.dumps({"channels": "non"}), encoding="utf-8")
    assert load_led_max(p) == DEFAULT_LED_MAX_MA
    p.write_text(json.dumps(["x", None]), encoding="utf-8")
    assert load_led_max(p) == DEFAULT_LED_MAX_MA


def test_load_led_max_values_clamped_to_driver_range(tmp_path) -> None:
    p = tmp_path / "led_max.json"
    p.write_text(json.dumps([99999, -5, 1000]), encoding="utf-8")
    assert load_led_max(p) == [2150, 0, 1000]


def test_led_max_file_for_sits_next_to_groups_json(tmp_path) -> None:
    recipes = tmp_path / "phs16lc" / "recipes"
    assert led_max_file_for(recipes) == tmp_path / "phs16lc" / "led_max.json"


def test_clamp_led_vector() -> None:
    vec, clamped = clamp_led_vector([2150] * 16, DEFAULT_LED_MAX_MA)
    assert vec == DEFAULT_LED_MAX_MA
    assert clamped == list(range(1, 17))
    # canaux sous le max : inchangés
    vec, clamped = clamp_led_vector([500] * 16, DEFAULT_LED_MAX_MA)
    assert vec == [500] * 16
    assert clamped == []
    # table plus courte que le vecteur : canaux hors table -> max driver (2150)
    vec, clamped = clamp_led_vector([2150, 2150], [1000])
    assert vec == [1000, 2150]
    assert clamped == [1]


def test_dim_vector_curve() -> None:
    recipe = [800] * 8 + [0] * 8
    # b=255 -> recette clampée ; b=1 -> ~74 mA (round(74+726/255)=77) ; b=0 -> éteint
    assert dim_vector(recipe, 255, DEFAULT_LED_MAX_MA) == recipe
    assert dim_vector(recipe, 1, DEFAULT_LED_MAX_MA) == [77] * 8 + [0] * 8
    assert dim_vector(recipe, 0, DEFAULT_LED_MAX_MA) == [0] * 16
    # b=128 : 74 + (800-74)*128/255 = 438
    assert dim_vector(recipe, 128, DEFAULT_LED_MAX_MA) == [438] * 8 + [0] * 8
    # la recette elle-même est clampée LED dans le dimmer : 2150 sur canal 3 (FR=1000)
    assert dim_vector([2150] * 16, 255, DEFAULT_LED_MAX_MA)[2] == 1000


def test_brightness_from_vector_roundtrip_and_fallback() -> None:
    recipe = [800] * 8 + [0] * 8
    for b in (1, 64, 128, 200, 255):
        currents = dim_vector(recipe, b, DEFAULT_LED_MAX_MA)
        assert brightness_from_vector(currents, recipe, DEFAULT_LED_MAX_MA) == b
    # recette éteinte -> None ; canal modifié hors dimmer (ex. set_channel externe) -> None
    assert brightness_from_vector([0] * 16, [0] * 16, DEFAULT_LED_MAX_MA) is None
    assert brightness_from_vector([2000] + [800] * 7 + [0] * 8, recipe, DEFAULT_LED_MAX_MA) is None


# ----------------------------------------------------------------------
# Intégration : clamp au niveau du lien + surcharge led_max.json
# ----------------------------------------------------------------------
async def _setup(hass, monkeypatch, bus, tmp_path, expected=1):
    recipes = tmp_path / "recipes"
    recipes.mkdir(exist_ok=True)
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**FLOW_DATA, "expected_spots": expected, "recipes_dir": str(recipes)},
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


async def test_set_channels_service_is_clamped_by_link(hass, monkeypatch, tmp_path) -> None:
    """D24 : le service set_channels envoie 2150 partout -> le lien clamp aux max LED."""
    bus = {1: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    clamp_events: list = []
    hass.bus.async_listen(EVENT_LED_CLAMPED, clamp_events.append)

    await hass.services.async_call(
        DOMAIN, "set_channels", {"address": "1", "currents": [2150] * 16}, blocking=True
    )
    await hass.async_block_till_done()
    assert coord.data.spots[1].currents == DEFAULT_LED_MAX_MA
    assert len(clamp_events) == 1
    assert clamp_events[0].data["address"] == 1
    assert len(clamp_events[0].data["clamped"]) == 16
    # la trame @SP réellement envoyée contient les valeurs clampées
    sp_frames = [s for s in FakePhsLink.instances[0].sent if s[0] == "SP"]
    assert sp_frames, "aucune trame @SP envoyée"
    sent_values = [int(v) for v in sp_frames[-1][2].split()]
    assert sent_values == DEFAULT_LED_MAX_MA


async def test_set_channel_service_is_clamped(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[500] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    # canal 3 = FR -> max 1000 mA
    await hass.services.async_call(
        DOMAIN, "set_channel", {"address": "1", "channel": 3, "ma": 2000}, blocking=True
    )
    await hass.async_block_till_done()
    assert coord.data.spots[1].currents[2] == 1000
    assert coord.data.spots[1].currents[0] == 500


async def test_led_max_json_overrides_default_table(hass, monkeypatch, tmp_path) -> None:
    """Surcharge par installation : led_max.json à côté de groups.json (parent de recipes_dir)."""
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    (tmp_path / "led_max.json").write_text(json.dumps([900] * 16), encoding="utf-8")
    bus = {1: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    # le coordinator a rechargé la table au premier polling
    assert coord.led_max == [900] * 16

    await hass.services.async_call(
        DOMAIN, "set_channels", {"address": "1", "currents": [2150] * 16}, blocking=True
    )
    await hass.async_block_till_done()
    assert coord.data.spots[1].currents == [900] * 16
