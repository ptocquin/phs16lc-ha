"""Tests de l'options flow (phase 7) : modification à chaud + rechargement."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.phs16lc.const import DOMAIN

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def _setup(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path):
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": 1, "recipes_dir": str(tmp_path)}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


async def test_options_flow_shows_form_with_current_values(hass, monkeypatch, tmp_path) -> None:
    entry, _ = await _setup(hass, monkeypatch, tmp_path)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    defaults = {}
    for k in result["data_schema"].schema:
        d = k.default
        defaults[str(k)] = (
            d() if callable(d) else d
        )  # voluptuous récent : default peut être une factory
    assert defaults["poll_interval"] == 10
    assert defaults["expected_spots"] == 1
    assert defaults["recipes_dir"] == str(tmp_path)


async def test_options_save_reloads_entry_with_new_poll_interval(
    hass, monkeypatch, tmp_path
) -> None:
    entry, coordinator = await _setup(hass, monkeypatch, tmp_path)
    assert coordinator.update_interval == timedelta(seconds=10)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"expected_spots": 4, "poll_interval": 30, "recipes_dir": str(tmp_path)},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["poll_interval"] == 30
    assert entry.options["expected_spots"] == 4
    # le update listener a rechargé l'entrée : nouveau coordinator, nouvel intervalle
    new_coordinator = hass.data[DOMAIN][entry.entry_id]
    assert new_coordinator is not coordinator
    assert new_coordinator.update_interval == timedelta(seconds=30)
    assert entry.state == ConfigEntryState.LOADED
