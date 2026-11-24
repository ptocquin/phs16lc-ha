"""Tests B2 : reconnexion automatique du port série (débranché/rebranché à chaud).

FakePhsLink.fail_io simule un port débranché (OSError dans send), fail_open
simule un port absent à la réouverture. Le coordinator doit fermer le port au
seuil LINK_ERROR_THRESHOLD, passer les entités en « unavailable », puis rouvrir
le port et rescanner la ligne dès qu'il réapparaît (états last_recipe conservés).
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.phs16lc.const import (
    DOMAIN,
    EVENT_LINK_LOST,
    EVENT_RECONNECTED,
    LINK_ERROR_THRESHOLD,
)

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA


async def _setup(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, bus: dict[int, FakeSpot]):
    FakePhsLink.reset(bus)
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    monkeypatch.setattr("custom_components.phs16lc.coordinator.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "expected_spots": len(bus)}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.state == ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id]


def _spot_state(hass: HomeAssistant, entry, address: int) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_spot_{address}_online"
    )
    assert entity_id is not None
    return hass.states.get(entity_id).state


async def _kill_link(hass: HomeAssistant, coordinator) -> None:
    """Simule le débranchement à chaud et pousse le coordinator au seuil de perte."""
    FakePhsLink.fail_io = True
    for _ in range(LINK_ERROR_THRESHOLD):
        await coordinator.async_refresh()
        await hass.async_block_till_done()


async def test_link_lost_after_threshold_marks_entities_unavailable(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot()}
    entry, coordinator = await _setup(hass, monkeypatch, bus)
    lost: list = []
    hass.bus.async_listen(EVENT_LINK_LOST, lost.append)
    old_link = FakePhsLink.instances[-1]
    assert _spot_state(hass, entry, 1) == "on"

    await _kill_link(hass, coordinator)

    assert coordinator.link is None
    assert coordinator.data.link is None
    assert old_link.closed is True  # port fermé au seuil
    assert len(lost) == 1 and lost[0].data["port"] == "/dev/fake0"
    assert coordinator.last_update_success is False
    assert _spot_state(hass, entry, 1) == "unavailable"
    assert _spot_state(hass, entry, 2) == "unavailable"


async def test_reconnect_when_port_comes_back_restores_state(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot(currents=[800] * 16), 2: FakeSpot()}
    entry, coordinator = await _setup(hass, monkeypatch, bus)
    reconnected: list = []
    hass.bus.async_listen(EVENT_RECONNECTED, reconnected.append)
    coordinator.data.spots[1].last_recipe = "croissance.json"  # D11 : doit survivre
    old_link = FakePhsLink.instances[-1]

    await _kill_link(hass, coordinator)
    assert coordinator.link is None

    FakePhsLink.fail_io = False  # l'adaptateur est rebranché
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    new_link = FakePhsLink.instances[-1]
    assert new_link is not old_link
    # D24 : coordinator.link est le wrapper LedClampLink (garde-fou LED) autour du lien réel
    assert getattr(coordinator.link, "wrapped", coordinator.link) is new_link
    assert coordinator.last_update_success is True
    assert len(reconnected) == 1
    assert reconnected[0].data["port"] == "/dev/fake0"
    assert sorted(reconnected[0].data["addresses"]) == [1, 2]  # rescan auto
    assert set(coordinator.data.spots) == {1, 2}
    assert coordinator.data.spots[1].last_recipe == "croissance.json"
    assert coordinator.data.spots[1].online is True
    assert coordinator.data.spots[1].currents == [800] * 16  # polling repris
    assert _spot_state(hass, entry, 1) == "on"


async def test_reconnect_attempts_are_rate_limited(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot()}
    _entry, coordinator = await _setup(hass, monkeypatch, bus)
    await _kill_link(hass, coordinator)
    assert coordinator.link is None
    attempts_after_kill = FakePhsLink.open_attempts

    FakePhsLink.fail_open = True  # le port ne réapparaît pas tout de suite
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert FakePhsLink.open_attempts == attempts_after_kill + 1  # une tentative
    assert coordinator.link is None
    assert coordinator.last_update_success is False

    await coordinator.async_refresh()  # dans la fenêtre RECONNECT_MIN_DELAY
    await hass.async_block_till_done()
    assert FakePhsLink.open_attempts == attempts_after_kill + 1  # pas de 2e tentative
    assert coordinator.link is None


async def test_command_while_link_dead_raises_homeassistanterror(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = {1: FakeSpot()}
    _entry, coordinator = await _setup(hass, monkeypatch, bus)
    await _kill_link(hass, coordinator)
    FakePhsLink.fail_open = True  # la reconnexion échoue aussi

    with pytest.raises(HomeAssistantError):  # UpdateFailed est un HomeAssistantError
        await coordinator.async_save(1)
    with pytest.raises(UpdateFailed):
        await coordinator.async_set_channels(1, [500] * 16)
    assert coordinator.link is None
