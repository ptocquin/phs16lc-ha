"""Tests du config flow et du setup de l'entrée (phase 1, FakePhsLink)."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.phs16lc.const import DOMAIN

from .fake_bus import FakePhsLink, FakeSpot

FLOW_DATA = {
    "port": "/dev/fake0",
    "expected_spots": 2,
    "poll_interval": 10,
    "recipes_dir": "/tmp/recipes",
}


async def test_config_flow_shows_user_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    keys = {str(k) for k in result["data_schema"].schema}
    assert {"port", "expected_spots", "poll_interval", "recipes_dir"} <= keys


async def test_setup_scans_line_and_creates_presence_sensors(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot(currents=[800] * 16), 2: FakeSpot()}
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FLOW_DATA)
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert set(coordinator.data.spots) == {1, 2}
    assert all(s.online for s in coordinator.data.spots.values())
    # @GP lu au premier polling
    assert coordinator.data.spots[1].currents == [800] * 16
    assert coordinator.data.spots[1].temperatures == (30.0, 31.0, 32.0)

    states = hass.states.async_all("binary_sensor")
    assert len(states) == 2
    assert {s.state for s in states} == {"on"}


async def test_duplicate_port_aborts(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": 1}
    )
    await hass.async_block_till_done()

    result2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result2 = await hass.config_entries.flow.async_configure(result2["flow_id"], FLOW_DATA)
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_form_offers_optional_rx_port(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    keys = {str(k) for k in result["data_schema"].schema}
    assert "rx_port" in keys


async def test_dual_box_stores_rx_port_and_opens_two_ports(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boîtier dual (2x USB-RS485-WE) : port TX + port RX distincts."""
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "rx_port": "/dev/fake1"}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    assert entry.data["rx_port"] == "/dev/fake1"
    link = FakePhsLink.instances[-1]
    assert link.tx_port == "/dev/fake0"
    assert link.rx_port == "/dev/fake1"
    assert not link.single_port


async def test_empty_rx_port_means_single_port(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FLOW_DATA)
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data.get("rx_port", "") == ""
    link = FakePhsLink.instances[-1]
    assert link.single_port
    assert link.rx_port == link.tx_port == "/dev/fake0"


async def test_rx_port_equal_to_tx_port_is_normalized(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "rx_port": "/dev/fake0"}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.data["rx_port"] == ""
    assert FakePhsLink.instances[-1].single_port
