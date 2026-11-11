"""Tests des capteurs (phase 5) : températures, courants, état de la ligne."""

from __future__ import annotations

import pytest
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import DOMAIN

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def _setup(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, bus: dict[int, FakeSpot], tmp_path, expected: int = 2):
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": expected, "recipes_dir": str(tmp_path)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _sensor_id(hass: HomeAssistant, entry, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id is not None, f"sensor {suffix} introuvable"
    return entity_id


async def test_temperature_sensors_per_spot(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(temps=(30.0, 31.5, 32.0)), 2: FakeSpot(temps=(40.0, 41.0, 42.0))}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)

    for address, temps in ((1, (30.0, 31.5, 32.0)), (2, (40.0, 41.0, 42.0))):
        for key, expected in zip(("cpu", "led1", "led2"), temps):
            state = hass.states.get(_sensor_id(hass, entry, f"spot_{address}_temp_{key}"))
            assert state is not None
            assert float(state.state) == expected
            assert state.attributes["device_class"] == "temperature"
            assert state.attributes["state_class"] == "measurement"
            assert state.attributes["unit_of_measurement"] == "°C"


async def test_currents_sensor_summary_and_channels_attribute(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(currents=[800] * 8 + [0] * 8)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)

    state = hass.states.get(_sensor_id(hass, entry, "spot_1_currents"))
    assert state.state == "800×8 + 0×8"
    assert state.attributes["channels"] == [800] * 8 + [0] * 8


async def test_sensors_unknown_when_spot_dead(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(temps=(30.0, 31.0, 32.0)), 2: FakeSpot(temps=(40.0, 41.0, 42.0))}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    bus[2].alive = False
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(_sensor_id(hass, entry, "spot_2_temp_cpu")).state == "unknown"
    assert hass.states.get(_sensor_id(hass, entry, "spot_2_currents")).state == "unknown"
    # la carte 1 continue de remonter
    assert float(hass.states.get(_sensor_id(hass, entry, "spot_1_temp_cpu")).state) == 30.0


async def test_line_status_sensor_on_hub(hass, monkeypatch, tmp_path) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    state = hass.states.get(_sensor_id(hass, entry, "line_status"))
    assert state.state == "2"
    assert state.attributes["online"] == [1, 2]
    assert state.attributes["offline"] == []

    bus[2].alive = False
    await coord.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(_sensor_id(hass, entry, "line_status"))
    assert state.state == "1"
    assert state.attributes["online"] == [1]
    assert state.attributes["offline"] == [2]
