"""Tests des boutons (phase 4) : save NVM, scènes, scan."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import DOMAIN, EVENT_SAVED, EVENT_SCANNED, EVENT_SCENE_APPLIED

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA

CROISSANCE = {"name": "croissance", "channels": [800] * 8 + [0] * 8}
SERRE = {"name": "serre", "targets": [{"address": 1, "recipe": "croissance.json"}]}


async def _setup(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, bus: dict[int, FakeSpot], tmp_path, expected: int = 1):
    recipes = tmp_path / "recipes"
    scenes = tmp_path / "scenes"
    recipes.mkdir()
    scenes.mkdir()
    (recipes / "croissance.json").write_text(json.dumps(CROISSANCE), encoding="utf-8")
    (scenes / "serre.json").write_text(json.dumps(SERRE), encoding="utf-8")
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": expected, "recipes_dir": str(recipes)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _button_id(hass: HomeAssistant, entry, unique_suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{entry.entry_id}_{unique_suffix}"
    )
    assert entity_id is not None, f"bouton {unique_suffix} introuvable"
    return entity_id


async def _press(hass, entity_id):
    await hass.services.async_call(BUTTON_DOMAIN, "press", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()


async def test_save_button_sends_wp_and_fires_event(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 16)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_SAVED, lambda e: events.append(e.data))

    await _press(hass, _button_id(hass, entry, "spot_1_save"))

    link = FakePhsLink.instances[0]
    assert ("WP", 1, "") in link.sent
    assert events == [{"address": 1, "ok": True}]


async def test_save_button_on_dead_card_raises_and_fires_error(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_SAVED, lambda e: events.append(e.data))

    bus[1].alive = False
    with pytest.raises(HomeAssistantError):
        await _press(hass, _button_id(hass, entry, "spot_1_save"))
    assert events[-1]["ok"] is False


async def test_scene_button_applies_scene_and_fires_event(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_SCENE_APPLIED, lambda e: events.append(e.data))

    await _press(hass, _button_id(hass, entry, "scene_serre"))

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[1].last_recipe == "croissance.json"
    assert events[-1]["scene"] == "serre.json"
    assert events[-1]["ok"] == 1
    assert events[-1]["errors"] == 0
    assert events[-1]["results"][0]["address"] == 1


async def test_scene_with_missing_recipe_reports_error_per_card(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    # scène qui référence une recette inexistante
    scenes = tmp_path / "scenes"
    (scenes / "cassee.json").write_text(
        json.dumps({"name": "cassee", "targets": [{"address": 1, "recipe": "inexistante.json"}]}),
        encoding="utf-8",
    )
    coord = hass.data[DOMAIN][entry.entry_id]
    await coord.async_refresh()  # le listener ajoute le bouton de la nouvelle scène
    await hass.async_block_till_done()

    events: list[dict] = []
    hass.bus.async_listen(EVENT_SCENE_APPLIED, lambda e: events.append(e.data))
    await _press(hass, _button_id(hass, entry, "scene_cassee"))

    assert events[-1]["ok"] == 0
    assert events[-1]["errors"] == 1
    assert events[-1]["results"][0]["ok"] is False


async def test_scan_button_discovers_new_spot(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=3)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_SCANNED, lambda e: events.append(e.data))

    assert len(hass.states.async_all("binary_sensor")) == 1
    bus[2] = FakeSpot()
    await _press(hass, _button_id(hass, entry, "scan"))

    assert set(coord.data.spots) == {1, 2}
    assert len(hass.states.async_all("binary_sensor")) == 2
    assert events[-1] == {"addresses": [1, 2], "count": 2}
