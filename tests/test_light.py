"""Tests de l'entité light (phase 2) : mapping mA↔brightness, turn_on/off, D11."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import DOMAIN, brightness_to_ma, ma_to_brightness
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


async def test_light_non_uniform_recipe_shows_max(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 8 + [0] * 8)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)
    s = hass.states.get(_light_id(hass, entry, 1))
    assert s.state == "on"
    assert s.attributes["brightness"] == ma_to_brightness(800)


# ----------------------------------------------------------------------
# Commandes
# ----------------------------------------------------------------------
async def test_turn_on_with_brightness_maps_to_ma(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    await _turn_on(hass, lid, brightness=255)
    assert coord.data.spots[1].currents == [2150] * 16
    assert hass.states.get(lid).attributes["brightness"] == 255

    await _turn_on(hass, lid, brightness=128)
    ma = brightness_to_ma(128)
    assert coord.data.spots[1].currents == [ma] * 16
    assert hass.states.get(lid).attributes["brightness"] == 128


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
    s = hass.states.get(lid)
    assert s.state == "on"
    assert s.attributes["brightness"] == ma_to_brightness(800)


async def test_turn_off_sends_zeros(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    await _turn_off(hass, lid)
    assert coord.data.spots[1].currents == [0] * 16
    assert hass.states.get(lid).state == "off"


async def test_turn_on_dead_card_raises_homeassistant_error(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    lid = _light_id(hass, entry, 1)

    bus[1].alive = False  # la carte ne répond plus
    with pytest.raises(HomeAssistantError):
        await _turn_on(hass, lid, brightness=100)
