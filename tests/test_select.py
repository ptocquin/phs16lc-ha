"""Tests des selects Recette/Groupe (phase 3)."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import (
    DEFAULT_LED_MAX_MA,
    DOMAIN,
    EVENT_RECIPE_APPLIED,
    clamp_led_vector,
)

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA

SPECTRE = {
    "name": "spectre",
    "groups": {
        "bleu": {"channels": [1, 2, 3, 4, 5, 6, 7, 8], "current": 1000},
        "rouge": {"channels": [9, 10, 11, 12, 13, 14, 15, 16], "current": 1200},
    },
}
CROISSANCE = {"name": "croissance", "channels": [800] * 8 + [0] * 8}


async def _setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, bus: dict[int, FakeSpot], tmp_path
):
    (tmp_path / "spectre.json").write_text(json.dumps(SPECTRE), encoding="utf-8")
    (tmp_path / "croissance.json").write_text(json.dumps(CROISSANCE), encoding="utf-8")
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": 1, "recipes_dir": str(tmp_path)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _select_id(hass: HomeAssistant, entry, address: int, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        SELECT_DOMAIN, DOMAIN, f"{entry.entry_id}_spot_{address}_{key}"
    )
    assert entity_id is not None, f"select {key} introuvable"
    return entity_id


async def _select(hass, entity_id, option):
    await hass.services.async_call(
        SELECT_DOMAIN, "select_option", {"entity_id": entity_id, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def test_recipe_select_lists_recipe_files(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    state = hass.states.get(_select_id(hass, entry, 1, "recipe"))
    assert state.attributes["options"] == ["croissance.json", "spectre.json"]
    assert state.state == "unknown"  # aucune recette sélectionnée


async def test_select_recipe_applies_full_recipe_and_fires_event(
    hass, monkeypatch, tmp_path
) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    events: list[dict] = []
    hass.bus.async_listen(EVENT_RECIPE_APPLIED, lambda e: events.append(e.data))

    rid = _select_id(hass, entry, 1, "recipe")
    await _select(hass, rid, "croissance.json")

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[1].last_recipe == "croissance.json"
    assert hass.states.get(rid).state == "croissance.json"
    assert events == [{"address": 1, "recipe": "croissance.json", "group": None, "ok": True}]


async def test_group_select_applies_partial_group(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    rid = _select_id(hass, entry, 1, "recipe")
    gid = _select_id(hass, entry, 1, "group")

    await _select(hass, rid, "spectre.json")  # bleu 1-8 à 1000, rouge 9-16 à 1200
    # D24 : 1200 mA dépasse le max des canaux FR 9 et 15 (1000 mA) -> clampés par le lien
    expected = clamp_led_vector([1000] * 8 + [1200] * 8, DEFAULT_LED_MAX_MA)[0]
    assert coord.data.spots[1].currents == expected
    assert coord.data.spots[1].currents[8] == 1000 and coord.data.spots[1].currents[14] == 1000

    # options du select Groupe = groupes de la recette courante
    assert hass.states.get(gid).attributes["options"] == ["bleu", "rouge"]

    # on modifie la base (ex: quelqu'un a changé les courants), puis on applique
    # seulement le groupe « bleu » : les canaux 9-16 doivent rester tels quels
    bus[1].currents = [500] * 16
    await coord.async_refresh()
    await hass.async_block_till_done()

    events: list[dict] = []
    hass.bus.async_listen(EVENT_RECIPE_APPLIED, lambda e: events.append(e.data))
    await _select(hass, gid, "bleu")

    # base relue à 500, canaux 1-8 patchés à 1000, canaux 9-16 inchangés à 500
    assert coord.data.spots[1].currents == [1000] * 8 + [500] * 8
    assert coord.data.spots[1].last_group == "bleu"
    assert hass.states.get(gid).state == "bleu"
    assert events[-1] == {"address": 1, "recipe": "spectre.json", "group": "bleu", "ok": True}


async def test_select_unknown_recipe_raises(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    rid = _select_id(hass, entry, 1, "recipe")
    with pytest.raises(HomeAssistantError):
        await _select(hass, rid, "nope.json")


async def test_group_select_without_recipe_raises(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    gid = _select_id(hass, entry, 1, "group")
    # aucune recette choisie -> options vides ; forcer l'appel direct lève une erreur
    with pytest.raises(HomeAssistantError):
        await _select(hass, gid, "bleu")


async def test_select_recipe_on_dead_card_fires_error_event(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_RECIPE_APPLIED, lambda e: events.append(e.data))

    bus[1].alive = False
    rid = _select_id(hass, entry, 1, "recipe")
    with pytest.raises(HomeAssistantError):
        await _select(hass, rid, "croissance.json")
    assert events[-1]["ok"] is False
    assert events[-1]["recipe"] == "croissance.json"
