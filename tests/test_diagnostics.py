"""Tests des diagnostics (phase 7)."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.phs16lc.const import DOMAIN
from custom_components.phs16lc.diagnostics import async_get_config_entry_diagnostics

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def test_diagnostics_collect_spot_info(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    bus = {1: FakeSpot(currents=[800] * 16, temps=(30.0, 31.0, 32.0)), 2: FakeSpot()}
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": 2, "recipes_dir": str(tmp_path)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED

    # la carte 2 tombe en panne après le scan initial
    bus[2].alive = False
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["link"]["port"] == "/dev/fake0"
    assert diag["entry"]["data"]["port"] == "/dev/fake0"
    assert "ports_detected" in diag

    spot1 = diag["spots"]["1"]
    assert spot1["online"] is True
    assert spot1["currents"] == [800] * 16
    assert spot1["temperatures"] == [30.0, 31.0, 32.0] or list(spot1["temperatures"]) == [
        30.0,
        31.0,
        32.0,
    ]
    assert tuple(spot1["identity"]) == (0x1234, "V1.0.7")  # #GI du FakePhsLink
    assert [tuple(b) for b in spot1["led_boards"]] == [(1, 0x11), (2, 0x22)]  # #GL

    spot2 = diag["spots"]["2"]
    assert spot2["online"] is False
    assert "identity" not in spot2  # pas de @GI/@GL sur carte muette


async def test_diagnostics_reports_dual_ports(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Montage dual : les diagnostics exposent tx_port et rx_port."""
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "rx_port": "/dev/fake1", "recipes_dir": str(tmp_path)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["link"]["port"] == "/dev/fake0"
    assert diag["link"]["tx_port"] == "/dev/fake0"
    assert diag["link"]["rx_port"] == "/dev/fake1"
    assert diag["link"]["single_port"] is False
