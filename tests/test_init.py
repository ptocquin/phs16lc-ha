"""Tests du coordinator et du cycle de vie de l'entrée (phase 1, FakePhsLink)."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import DOMAIN

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def _setup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    bus: dict[int, FakeSpot],
    expected: int = 2,
):
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": expected}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _entity_id(hass: HomeAssistant, entry, address: int, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_spot_{address}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def test_polling_marks_dead_spot_offline(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot()}
    entry, coordinator = await _setup(hass, monkeypatch, bus)

    bus[2].alive = False  # carte 2 ne répond plus
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.spots[2].online is False
    assert coordinator.data.spots[2].currents is None
    assert hass.states.get(_entity_id(hass, entry, 2, "online")).state == "off"
    assert hass.states.get(_entity_id(hass, entry, 1, "online")).state == "on"


async def test_rescan_discovers_new_spots(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot()}
    _entry, coordinator = await _setup(hass, monkeypatch, bus, expected=3)
    assert set(coordinator.data.spots) == {1}
    assert len(hass.states.async_all("binary_sensor")) == 1

    bus[2] = FakeSpot()
    bus[3] = FakeSpot()
    found = await coordinator.async_rescan()
    await hass.async_block_till_done()

    assert found == [1, 2, 3]
    assert set(coordinator.data.spots) == {1, 2, 3}
    assert len(hass.states.async_all("binary_sensor")) == 3


async def test_unload_closes_serial_port(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot()}
    entry, _ = await _setup(hass, monkeypatch, bus, expected=1)
    link = FakePhsLink.instances[0]

    ok = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert ok is True
    assert link.closed is True
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_setup_retries_when_port_unavailable(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenLink:
        def __init__(self, port, *a, **kw):
            raise OSError(19, "Device not configured")

    monkeypatch.setattr("custom_components.phs16lc.PhsLink", BrokenLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FLOW_DATA)
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.state == ConfigEntryState.SETUP_RETRY  # ConfigEntryNotReady -> retry auto
