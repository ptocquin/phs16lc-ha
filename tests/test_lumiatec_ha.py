"""Tests HA de la famille lumiatec : config flow `family`, scan, polling, light.

Faux bus lumiatec (FakeLumLink) + un test E2E pty via tools/fake_lumiatec.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.phs16lc.const import (
    CONF_FAMILY,
    DOMAIN,
    FAMILY_LUMIATEC,
    FAMILY_PHS16LC,
    brightness_to_ma,
    ma_to_brightness,
    min_on_ma,
)
from custom_components.phs16lc.coordinator import _poll_spots, _rescan
from custom_components.phs16lc.phs16ctl.link import PhsLink
from custom_components.phs16lc.phs16ctl.lumiatec import LUMIATEC

from .fake_lumiatec_bus import FakeLumLink, FakeLumSpot
from .test_config_flow import FLOW_DATA

REPO = Path(__file__).resolve().parents[2]
FAKE_SIM = REPO / "phs16ctl" / "tools" / "fake_lumiatec.py"

LUM_FLOW_DATA = {**FLOW_DATA, CONF_FAMILY: FAMILY_LUMIATEC, "expected_spots": 255}


async def _setup_lum(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    bus: dict[int, FakeLumSpot],
    flow_data=None,
    physical_first: int | None = None,
):
    FakeLumLink.reset(bus)
    FakeLumLink.physical_first = physical_first
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakeLumLink)
    monkeypatch.setattr("custom_components.phs16lc.coordinator.PhsLink", FakeLumLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], flow_data or {**LUM_FLOW_DATA, "recipes_dir": "/tmp/recipes"}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _light_id(hass: HomeAssistant, entry, address: int) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, f"{entry.entry_id}_spot_{address}_light"
    )
    assert entity_id is not None
    return entity_id


# --- Mapping luminosité par famille (const) --------------------------------


def test_brightness_mapping_phs16lc_unchanged():
    assert brightness_to_ma(255) == 2150 and brightness_to_ma(0) == 0
    assert ma_to_brightness(2150) == 255 and ma_to_brightness(0) == 0
    assert min_on_ma(FAMILY_PHS16LC) == 74
    # mapping linéaire historique : brightness 1 -> ~82 mA (74 + 2076/255)
    assert brightness_to_ma(1) == round(74 + (2150 - 74) / 255)


def test_brightness_mapping_lumiatec():
    # 1..255 -> step 1..87 -> mA (5,7 mA/step, plafond 496)
    assert brightness_to_ma(255, FAMILY_LUMIATEC) == 496
    assert brightness_to_ma(1, FAMILY_LUMIATEC) == 6
    assert brightness_to_ma(0, FAMILY_LUMIATEC) == 0
    assert ma_to_brightness(496, FAMILY_LUMIATEC) == 255
    assert ma_to_brightness(0, FAMILY_LUMIATEC) == 0
    assert min_on_ma(FAMILY_LUMIATEC) == 1


# --- Config flow : family ----------------------------------------------------


async def test_config_flow_default_family_is_phs16lc(hass: HomeAssistant, monkeypatch) -> None:
    from .fake_bus import FakePhsLink, FakeSpot

    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    keys = {str(k) for k in result["data_schema"].schema}
    assert "family" in keys  # champ présent
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FLOW_DATA)
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.data[CONF_FAMILY] == FAMILY_PHS16LC  # défaut
    assert entry.title == f"PHS16-LC {FLOW_DATA['port']}"


async def test_config_flow_family_lumiatec(hass: HomeAssistant, monkeypatch) -> None:
    bus = {131: FakeLumSpot(serial=0x14100083), 136: FakeLumSpot()}
    entry, coordinator = await _setup_lum(hass, monkeypatch, bus)
    assert entry.data[CONF_FAMILY] == FAMILY_LUMIATEC
    assert entry.title == f"lumiatec {FLOW_DATA['port']}"
    assert coordinator.family == FAMILY_LUMIATEC
    assert set(coordinator.data.spots) == {131, 136}  # scan 1..255, adresses non contiguës
    # le lien porte le dialect lumiatec
    assert FakeLumLink.instances[-1].dialect is LUMIATEC


async def test_options_flow_has_family(hass: HomeAssistant, monkeypatch) -> None:
    bus = {136: FakeLumSpot()}
    entry, _ = await _setup_lum(hass, monkeypatch, bus)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    keys = {str(k) for k in result["data_schema"].schema}
    assert "family" in keys
    assert "master_addr" in keys


async def test_lumiatec_master_addr_option_overrides_election(hass, monkeypatch) -> None:
    """Option master_addr explicite : prioritaire sur l'élection auto @GE."""
    bus = {131: FakeLumSpot(serial=0x14100083), 136: FakeLumSpot()}
    # physical_first=None : l'auto élirait 131 (min) ; l'option force 136
    flow_data = {**LUM_FLOW_DATA, "master_addr": 136, "recipes_dir": "/tmp/recipes"}
    entry, coordinator = await _setup_lum(hass, monkeypatch, bus, flow_data=flow_data)
    assert entry.data["master_addr"] == 136
    assert coordinator._master_addr == 136
    link = FakeLumLink.instances[-1]
    sf = [(a, p) for c, a, p in link.sent if c == "SF"]
    assert (136, "3") in sf and (131, "1") in sf


# --- Polling + light ----------------------------------------------------------


async def test_poll_reads_currents_and_temps_lumiatec(hass, monkeypatch) -> None:
    bus = {131: FakeLumSpot(serial=0x14100083, channels=[35] * 16), 136: FakeLumSpot()}
    _, coordinator = await _setup_lum(hass, monkeypatch, bus)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.spots[131].currents == [200] * 16  # step 35 x 5,7 mA
    assert coordinator.data.spots[136].currents == [0] * 16
    assert coordinator.data.spots[131].temperatures == (30.0, 21.4, 21.4)


async def test_light_turn_on_lumiatec_slave_sends_sf1_and_sc(hass, monkeypatch) -> None:
    bus = {131: FakeLumSpot(serial=0x14100083), 136: FakeLumSpot()}
    entry, _ = await _setup_lum(hass, monkeypatch, bus)
    light_id = _light_id(hass, entry, 136)

    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": light_id, "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()

    link = FakeLumLink.instances[-1]
    sf = [(a, p) for c, a, p in link.sent if c == "SF"]
    sc = [(a, p) for c, a, p in link.sent if c == "SC"]
    assert (136, "1") in sf  # 136 = slave (master = 131, plus petite adresse)
    assert all(p.endswith(" 0 200") for _, p in sc)
    # brightness 128 -> step 44 -> 251 mA -> step 44 en retour
    assert (136, "0 44 0 200") in sc
    state = hass.states.get(light_id)
    assert state.state == "on"
    assert state.attributes["brightness"] in (128, 129)  # round-trip mA->step->brightness


async def test_light_turn_on_lumiatec_master_sends_sf3(hass, monkeypatch) -> None:
    bus = {131: FakeLumSpot(serial=0x14100083), 136: FakeLumSpot()}
    entry, _ = await _setup_lum(hass, monkeypatch, bus)
    light_id = _light_id(hass, entry, 131)  # 131 = master (min)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()
    link = FakeLumLink.instances[-1]
    assert ("SF", 131, "3") in [(c, a, p) for c, a, p in link.sent if c == "SF"]
    assert ("SC", 131, "0 87 0 200") in [(c, a, p) for c, a, p in link.sent if c == "SC"]
    assert hass.states.get(light_id).attributes["brightness"] == 255


async def test_lumiatec_master_elected_by_ge_not_min_address(hass, monkeypatch) -> None:
    """Prod 2026-11-20 : le master est le spot physiquement premier (validé @GE OK),
    pas la plus petite adresse — sur le bus 131/136 c'est 136, pas 131."""
    bus = {131: FakeLumSpot(serial=0x14100083), 136: FakeLumSpot()}
    # seul un master posé sur 136 (physiquement premier) donne @GE OK
    entry, coordinator = await _setup_lum(hass, monkeypatch, bus, physical_first=136)
    assert coordinator._master_addr == 136  # élu au scan initial via @GE
    light_id = _light_id(hass, entry, 131)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_on", {"entity_id": light_id, "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()
    link = FakeLumLink.instances[-1]
    sf = [(a, p) for c, a, p in link.sent if c == "SF"]
    assert (131, "1") in sf  # 131 = slave (power seul)
    assert (136, "3") in sf  # 136 = master (power+master)
    sc = [(a, p) for c, a, p in link.sent if c == "SC"]
    assert all(a == 131 for a, _ in sc)  # seuls les canaux de 131 sont réglés


async def test_light_turn_off_lumiatec(hass, monkeypatch) -> None:
    bus = {136: FakeLumSpot(channels=[44] * 16)}
    entry, coordinator = await _setup_lum(hass, monkeypatch, bus)
    light_id = _light_id(hass, entry, 136)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(light_id).state == "on"
    await hass.services.async_call(LIGHT_DOMAIN, "turn_off", {"entity_id": light_id}, blocking=True)
    await hass.async_block_till_done()
    link = FakeLumLink.instances[-1]
    assert ("SC", 136, "0 0 0 200") in [(c, a, p) for c, a, p in link.sent if c == "SC"]
    assert hass.states.get(light_id).state == "off"


# --- E2E pty : chemin vendored réel (PhsLink dialect LUMIATEC) + simulateur -----


def test_e2e_rescan_and_poll_on_pty() -> None:
    proc = subprocess.Popen(
        [sys.executable, str(FAKE_SIM), "--address", "136", "--duration", "90"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        port = proc.stdout.readline().strip()
        assert port.startswith("/dev/")
        with PhsLink(port, dialect=LUMIATEC) as link:
            found = _rescan(link, 140, FAMILY_LUMIATEC)  # balayage 1..140 (0,2 s de silence max)
            assert found == [136]
            from custom_components.phs16lc.coordinator import SpotState

            spots = {136: SpotState(address=136, online=True)}
            _poll_spots(link, spots, FAMILY_LUMIATEC)
            assert spots[136].online is True
            assert spots[136].currents == [0] * 16
            assert spots[136].temperatures == (30.0, 21.39, 21.35)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
