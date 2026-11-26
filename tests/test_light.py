"""Tests de l'entité light (phase 2 + D23/D24) : mapping mA↔brightness, turn_on/off,
dimmer de recette (slider), clamp LED, D11."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import (
    DEFAULT_LED_MAX_MA,
    DOMAIN,
    EVENT_DIMMED,
    EVENT_LED_CLAMPED,
    brightness_to_ma,
    clamp_led_vector,
    dim_vector,
    ma_to_brightness,
)
from custom_components.phs16lc.phs16ctl.controller import DEFAULT_CURRENT_MA

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def _setup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    bus: dict[int, FakeSpot],
    recipes_dir,
    expected: int = 1,
):
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**FLOW_DATA, "expected_spots": expected, "recipes_dir": str(recipes_dir)},
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _light_id(hass: HomeAssistant, entry, address: int) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, f"{entry.entry_id}_spot_{address}_light"
    )
    assert entity_id is not None, "entité light introuvable"
    return entity_id


async def _turn_on(hass, entity_id, **kwargs):
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": entity_id, **kwargs}, blocking=True
    )
    await hass.async_block_till_done()


async def _turn_off(hass, entity_id):
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


# ----------------------------------------------------------------------
# Mapping (tests purs)
# ----------------------------------------------------------------------
def test_brightness_ma_mapping() -> None:
    assert brightness_to_ma(0) == 0
    assert brightness_to_ma(255) == 2150
    assert brightness_to_ma(1) == round(74 + (2150 - 74) / 255)
    assert ma_to_brightness(0) == 0
    assert ma_to_brightness(73) == 0
    assert ma_to_brightness(74) == 1  # allumé → au moins 1
    assert ma_to_brightness(2150) == 255
    # aller-retour cohérent à ±1 près
    for b in (1, 50, 128, 200, 255):
        assert (
            abs(brightness_to_ma(ma_to_brightness(brightness_to_ma(b))) - brightness_to_ma(b)) <= 9
        )


# ----------------------------------------------------------------------
# État reflété par le polling
# ----------------------------------------------------------------------
async def test_light_state_reflects_currents(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 16), 2: FakeSpot(currents=[0] * 16)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path, expected=2)

    s1 = hass.states.get(_light_id(hass, entry, 1))
    assert s1.state == "on"
    assert s1.attributes["brightness"] == ma_to_brightness(800)

    s2 = hass.states.get(_light_id(hass, entry, 2))
    assert s2.state == "off"


async def test_light_exposes_fan_settings_attributes(hass, monkeypatch, tmp_path) -> None:
    """Les paramètres ventilateur lus au polling (@GF) sont exposés en attributs du light
    (affichés par la carte Lovelace dans la vue dépliée, sous les températures)."""
    bus = {1: FakeSpot(fan=(42, 66, 20))}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)

    assert coord.data.spots[1].fan_settings is not None
    s = hass.states.get(_light_id(hass, entry, 1))
    assert s.attributes["fan_low_temp"] == 42
    assert s.attributes["fan_high_temp"] == 66
    assert s.attributes["fan_min_duty"] == 20


async def test_light_non_uniform_recipe_shows_max(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 8 + [0] * 8)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)
    s = hass.states.get(_light_id(hass, entry, 1))
    assert s.state == "on"
    assert s.attributes["brightness"] == ma_to_brightness(800)


# ----------------------------------------------------------------------
# Commandes
# ----------------------------------------------------------------------
async def test_turn_on_brightness_without_recipe_raises(hass, monkeypatch, tmp_path) -> None:
    """D23 : sans recette choisie, le slider est inactif (erreur explicite, aucun @SP)."""
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    with pytest.raises(HomeAssistantError, match="recette"):
        await _turn_on(hass, lid, brightness=200)
    assert coord.data.spots[1].currents == [0] * 16  # rien envoyé


async def test_turn_on_brightness_dims_last_recipe(hass, monkeypatch, tmp_path) -> None:
    """D23 : le slider dimme la dernière recette canal par canal (jamais uniforme)."""
    (tmp_path / "croissance.json").write_text(
        json.dumps({"name": "croissance", "channels": [800] * 8 + [0] * 8}), encoding="utf-8"
    )
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)
    coord.data.spots[1].last_recipe = "croissance.json"
    dimmed_events: list = []
    hass.bus.async_listen(EVENT_DIMMED, dimmed_events.append)

    # b=255 -> recette à 100 % (800 < max LED des canaux 1-8 -> pas de clamp)
    await _turn_on(hass, lid, brightness=255)
    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert hass.states.get(lid).attributes["brightness"] == 255
    assert coord.data.spots[1].last_vector == [800] * 8 + [0] * 8

    # b=128 -> courbe linéaire 74..800 : ma = 74 + (800-74)*128/255 = 438
    await _turn_on(hass, lid, brightness=128)
    expected = dim_vector([800] * 8 + [0] * 8, 128, DEFAULT_LED_MAX_MA)
    assert coord.data.spots[1].currents == expected
    assert expected[:8] == [438] * 8 and expected[8:] == [0] * 8
    assert hass.states.get(lid).attributes["brightness"] == 128
    assert len(dimmed_events) == 2
    assert dimmed_events[1].data["dim_percent"] == round(100 * 128 / 255)


async def test_turn_on_brightness_clamps_recipe_to_led_max(hass, monkeypatch, tmp_path) -> None:
    """D24 : une recette qui dépasse le max LED d'un canal est clampée (canaux FR=1000)."""
    (tmp_path / "floraison.json").write_text(
        json.dumps({"name": "floraison", "channels": [1200] * 16}), encoding="utf-8"
    )
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)
    coord.data.spots[1].last_recipe = "floraison.json"
    clamp_events: list = []
    hass.bus.async_listen(EVENT_LED_CLAMPED, clamp_events.append)

    await _turn_on(hass, lid, brightness=255)
    clamped, channels = clamp_led_vector([1200] * 16, DEFAULT_LED_MAX_MA)
    assert coord.data.spots[1].currents == clamped
    assert channels == [3, 5, 9, 15]  # canaux FR à 1000 mA
    assert coord.data.spots[1].last_vector == clamped
    assert len(clamp_events) == 1
    assert [c["channel"] for c in clamp_events[0].data["clamped"]] == [3, 5, 9, 15]
    # le slider affiche toujours 255 : la recette à 100 % EST le clampé
    assert hass.states.get(lid).attributes["brightness"] == 255


async def test_turn_on_without_brightness_uses_default_ma(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    await _turn_on(hass, lid)
    assert coord.data.spots[1].currents == [DEFAULT_CURRENT_MA] * 16
    assert hass.states.get(lid).state == "on"


async def test_turn_on_without_brightness_reapplies_last_recipe(
    hass, monkeypatch, tmp_path
) -> None:
    (tmp_path / "croissance.json").write_text(
        json.dumps({"name": "croissance", "channels": [800] * 8 + [0] * 8}), encoding="utf-8"
    )
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)
    coord.data.spots[1].last_recipe = "croissance.json"  # comme le select de la phase 3

    await _turn_on(hass, lid)
    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[1].last_vector == [800] * 8 + [0] * 8
    s = hass.states.get(lid)
    assert s.state == "on"
    # D23 : le slider affiche le % de la recette (100 %), pas le courant max (D10)
    assert s.attributes["brightness"] == 255
    assert s.attributes["recette"] == "croissance.json"
    assert s.attributes["channels_ma"] == [800] * 8 + [0] * 8
    assert s.attributes["led_max"] == DEFAULT_LED_MAX_MA


async def test_turn_off_sends_zeros(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    await _turn_off(hass, lid)
    assert coord.data.spots[1].currents == [0] * 16
    assert hass.states.get(lid).state == "off"


async def test_turn_on_dead_card_raises_homeassistant_error(hass, monkeypatch, tmp_path) -> None:
    (tmp_path / "croissance.json").write_text(
        json.dumps({"name": "croissance", "channels": [800] * 16}), encoding="utf-8"
    )
    bus = {1: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)
    coord.data.spots[1].last_recipe = "croissance.json"

    bus[1].alive = False  # la carte ne répond plus
    with pytest.raises(HomeAssistantError):
        await _turn_on(hass, lid, brightness=100)
