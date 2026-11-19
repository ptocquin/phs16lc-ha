"""Tests des services phs16lc.* (phase 6)."""

from __future__ import annotations

import json

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.phs16lc.const import DOMAIN, EVENT_RECIPE_APPLIED, EVENT_SAVED

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA

CROISSANCE = {"name": "croissance", "channels": [800] * 8 + [0] * 8}
SERRE = {
    "name": "serre",
    "targets": [
        {"address": 1, "recipe": "croissance.json"},
        {"address": 2, "recipe": "croissance.json"},
    ],
}


async def _setup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    bus: dict[int, FakeSpot],
    tmp_path,
    expected: int = 2,
):
    recipes = tmp_path / "recipes"
    scenes = tmp_path / "scenes"
    recipes.mkdir(exist_ok=True)
    scenes.mkdir(exist_ok=True)
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


async def _call(hass, service: str, data: dict):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


async def test_services_registered_on_setup(hass, monkeypatch, tmp_path) -> None:
    await _setup(hass, monkeypatch, {1: FakeSpot()}, tmp_path, expected=1)
    for service in (
        "scan",
        "apply_recipe",
        "apply_scene",
        "save",
        "set_channels",
        "set_channel",
        "set_group",
        "remove_group",
    ):
        assert hass.services.has_service(DOMAIN, service), service


async def test_apply_recipe_service_single_address(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_RECIPE_APPLIED, lambda e: events.append(e.data))

    await _call(hass, "apply_recipe", {"address": "1", "recipe": "croissance.json"})

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[2].currents == [0] * 16  # carte 2 inchangée
    assert events[-1] == {"address": 1, "recipe": "croissance.json", "group": None, "ok": True}


async def test_apply_recipe_service_all_addresses(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    await _call(hass, "apply_recipe", {"address": "all", "recipe": "croissance.json"})

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[2].currents == [800] * 8 + [0] * 8


async def test_apply_recipe_unknown_address_raises(hass, monkeypatch, tmp_path) -> None:
    await _setup(hass, monkeypatch, {1: FakeSpot()}, tmp_path, expected=1)
    with pytest.raises(HomeAssistantError):
        await _call(hass, "apply_recipe", {"address": "9", "recipe": "croissance.json"})


async def test_apply_scene_service_with_save(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    await _call(hass, "apply_scene", {"file": "serre.json", "save": True})

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[2].currents == [800] * 8 + [0] * 8
    link = FakePhsLink.instances[0]
    assert ("WP", 1, "") in link.sent and ("WP", 2, "") in link.sent  # save=true -> @WP par carte


async def test_save_service(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[500] * 16)}
    await _setup(hass, monkeypatch, bus, tmp_path, expected=1)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_SAVED, lambda e: events.append(e.data))

    await _call(hass, "save", {"address": "1"})

    assert ("WP", 1, "") in FakePhsLink.instances[0].sent
    assert events[-1] == {"address": 1, "ok": True}


async def test_set_channels_service_string_and_count_check(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)

    await _call(
        hass, "set_channels", {"address": "1", "currents": "800 800 0 0 0 0 0 0 0 0 0 0 0 0 0 0"}
    )
    assert coord.data.spots[1].currents == [800, 800] + [0] * 14

    # mauvais nombre de canaux (carte 16 canaux, 8 fournis) -> erreur de validation
    with pytest.raises(HomeAssistantError):
        await _call(
            hass, "set_channels", {"address": "1", "currents": "800 800 800 800 800 800 800 800"}
        )

    # la liste JSON fonctionne aussi
    await _call(hass, "set_channels", {"address": "1", "currents": [1000] * 16})
    assert coord.data.spots[1].currents == [1000] * 16


async def test_set_channel_service_patches_one_channel(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)

    await _call(hass, "set_channel", {"address": "1", "channel": 3, "ma": 0})
    assert coord.data.spots[1].currents == [800, 800, 0] + [800] * 13

    with pytest.raises(HomeAssistantError):
        await _call(hass, "set_channel", {"address": "1", "channel": 17, "ma": 100})


async def test_scan_service(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot()}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=2)
    bus[2] = FakeSpot()

    await _call(hass, "scan", {})

    assert set(coord.data.spots) == {1, 2}


async def test_services_removed_on_last_unload(hass, monkeypatch, tmp_path) -> None:
    entry, _ = await _setup(hass, monkeypatch, {1: FakeSpot()}, tmp_path, expected=1)
    assert hass.services.has_service(DOMAIN, "scan")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, "scan")
