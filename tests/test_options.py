"""Tests de l'options flow (phase 7) : modification à chaud + rechargement."""

from __future__ import annotations

from datetime import timedelta

import pytest
import voluptuous as vol
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
        if d is not vol.UNDEFINED:
            defaults[str(k)] = d() if callable(d) else d  # default peut être une factory
        else:
            # pas de default= : pré-remplissage via suggested_value (ex. rx_port)
            defaults[str(k)] = (k.description or {}).get("suggested_value")
    assert defaults["poll_interval"] == 10
    assert defaults["expected_spots"] == 1
    assert defaults["recipes_dir"] == str(tmp_path)
    # B3 : port et rx_port proposés avec leurs valeurs courantes
    assert defaults["port"] == "/dev/fake0"
    assert defaults["rx_port"] == ""


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


async def _options(hass, entry, **overrides):
    """Lance l'options flow et le valide avec les valeurs courantes + overrides."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    data = {
        "port": str(entry.options.get("port", entry.data["port"])),
        "rx_port": str(entry.options.get("rx_port", entry.data.get("rx_port", "")) or ""),
        "master_addr": int(entry.options.get("master_addr", entry.data.get("master_addr", 0))),
        "expected_spots": int(entry.options.get("expected_spots", entry.data["expected_spots"])),
        "poll_interval": int(entry.options.get("poll_interval", entry.data["poll_interval"])),
        "recipes_dir": str(entry.options.get("recipes_dir", entry.data["recipes_dir"])),
    }
    data.update(overrides)
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def test_options_change_port_reloads_entry_on_new_port(hass, monkeypatch, tmp_path) -> None:
    """B3 : changer le port dans l'options flow rouvre le nouveau port au rechargement."""
    entry, coordinator = await _setup(hass, monkeypatch, tmp_path)
    old_link = FakePhsLink.instances[-1]
    assert old_link.tx_port == "/dev/fake0"

    result = await _options(hass, entry, port="/dev/fake9")
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["port"] == "/dev/fake9"
    assert entry.unique_id == "/dev/fake9"  # le doublon sur ce port reste bloqué
    assert entry.title == "PHS16-LC /dev/fake9"
    assert old_link.closed is True  # ancien port fermé au rechargement
    new_link = FakePhsLink.instances[-1]
    assert new_link.tx_port == "/dev/fake9"
    assert new_link is not old_link
    new_coordinator = hass.data[DOMAIN][entry.entry_id]
    assert new_coordinator is not coordinator
    # D24 : coordinator.link est le wrapper LedClampLink (garde-fou LED) autour du lien réel
    assert getattr(new_coordinator.link, "wrapped", new_coordinator.link) is new_link
    assert entry.state == ConfigEntryState.LOADED


async def test_options_rx_port_equal_to_port_is_normalized(hass, monkeypatch, tmp_path) -> None:
    """B3 : rx_port identique au port TX => normalisé en '' (montage à un port)."""
    entry, _ = await _setup(hass, monkeypatch, tmp_path)
    result = await _options(hass, entry, rx_port="/dev/fake0")
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["rx_port"] == ""
    assert FakePhsLink.instances[-1].single_port


async def test_options_dual_box_rx_port_opens_two_ports(hass, monkeypatch, tmp_path) -> None:
    """B3 : rx_port distinct du port TX en options flow => montage dual rechargé."""
    entry, _ = await _setup(hass, monkeypatch, tmp_path)
    result = await _options(hass, entry, rx_port="/dev/fake1")
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["rx_port"] == "/dev/fake1"
    link = FakePhsLink.instances[-1]
    assert link.tx_port == "/dev/fake0"
    assert link.rx_port == "/dev/fake1"
    assert not link.single_port


async def test_options_clearing_rx_port_empties_it(hass, monkeypatch, tmp_path) -> None:
    """Régression (prod 2026-11-20) : vider le champ RX dans l'options flow doit vider rx_port.

    Le frontend omet la clé quand le champ optionnel est vidé ; avec un `default=`
    voluptuous, l'ancienne valeur était réinjectée et re-sauvegardée. On soumet
    donc SANS la clé rx_port, comme le fait le frontend.
    """
    entry, _ = await _setup(hass, monkeypatch, tmp_path)
    result = await _options(hass, entry, rx_port="/dev/fake1")  # montage dual
    await hass.async_block_till_done()
    assert entry.options["rx_port"] == "/dev/fake1"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    data = {
        "port": "/dev/fake0",
        # "rx_port" volontairement absent : champ vidé côté frontend
        "expected_spots": 1,
        "poll_interval": 10,
        "recipes_dir": str(tmp_path),
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], data)
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["rx_port"] == ""  # vidé, pas réinjecté
    link = FakePhsLink.instances[-1]
    assert link.single_port  # retour au montage à un seul port
    assert entry.state == ConfigEntryState.LOADED


async def test_options_port_conflict_with_other_entry_shows_error(
    hass, monkeypatch, tmp_path
) -> None:
    """B3 : un port déjà utilisé par une autre entrée est refusé avec une erreur."""
    entry_a, _ = await _setup(hass, monkeypatch, tmp_path)  # port /dev/fake0
    FakePhsLink.reset({1: FakeSpot()})
    monkeypatch.setattr("custom_components.phs16lc.PhsLink", FakePhsLink)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FLOW_DATA, "port": "/dev/fake1", "expected_spots": 1}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry_b = result["result"]
    assert entry_b.unique_id == "/dev/fake1"

    result = await _options(hass, entry_a, port="/dev/fake1")
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM  # formulaire ré-affiché avec l'erreur
    assert result["errors"] == {"base": "already_configured"}
    assert entry_a.unique_id == "/dev/fake0"  # inchangé
    assert entry_a.options.get("port", "/dev/fake0") == "/dev/fake0"  # options non modifiées
