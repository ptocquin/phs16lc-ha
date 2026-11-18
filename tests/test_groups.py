"""Tests des groupes de luminaires (phase 10) + copie des données embarquées.

Couvre : parsing de groups.json, chargement à chaud, entités de groupe
(light/select/button), commandes du coordinator, services `group:<id>`, labels
colorés + areas posés sur les devices membres, copie auto des recettes/scènes.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

import custom_components.phs16lc as phs16lc
from custom_components.phs16lc.const import (
    DOMAIN,
    EVENT_GROUP_RECIPE_APPLIED,
    EVENT_RECIPE_APPLIED,
)
from custom_components.phs16lc.groups import GroupDef, load_groups

from .fake_bus import FakePhsLink, FakeSpot
from .test_config_flow import FLOW_DATA

CROISSANCE = {"name": "croissance", "channels": [800] * 8 + [0] * 8}

GROUPS = {
    "serre_1_nord": {
        "name": "Serre 1 — Nord",
        "color": "#4CAF50",
        "icon": "mdi:leaf",
        "area": "serre_1",
        "addresses": [1, 2],
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recipes_dir(tmp_path: Path, groups: dict | None = GROUPS) -> Path:
    """Prépare <tmp>/phs16lc/{recipes,scenes,groups.json} et retourne le dossier recipes."""
    base = tmp_path / "phs16lc"
    recipes = base / "recipes"
    scenes = base / "scenes"
    recipes.mkdir(parents=True, exist_ok=True)
    scenes.mkdir(parents=True, exist_ok=True)
    (recipes / "croissance.json").write_text(json.dumps(CROISSANCE), encoding="utf-8")
    (scenes / "serre.json").write_text(
        json.dumps({"name": "serre", "targets": []}), encoding="utf-8"
    )
    if groups is not None:
        (base / "groups.json").write_text(json.dumps(groups), encoding="utf-8")
    return recipes


async def _setup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    bus: dict[int, FakeSpot],
    tmp_path: Path,
    groups: dict | None = GROUPS,
    expected: int = 2,
):
    recipes = _recipes_dir(tmp_path, groups)
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


def _entity_id(hass: HomeAssistant, platform: str, entry, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, f"entité {platform} {unique_id} introuvable"
    return entity_id


async def _call(hass, domain: str, service: str, data: dict):
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# load_groups (unitaire)
# ---------------------------------------------------------------------------


def test_load_groups_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_groups(tmp_path / "groups.json") == {}


def test_load_groups_invalid_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "groups.json"
    p.write_text("{ pas du json", encoding="utf-8")
    assert load_groups(p) == {}


def test_load_groups_parsing_and_validation(tmp_path: Path) -> None:
    p = tmp_path / "groups.json"
    p.write_text(
        json.dumps(
            {
                "ok_group": {"name": "Groupe OK", "color": "#FF0000", "addresses": [1, 2]},
                "bad id!": {"addresses": [3]},  # id invalide -> ignoré
                "no_addr": {"addresses": []},  # sans adresse -> ignoré
                "bad_addr": {"addresses": ["x"]},  # adresses invalides -> ignoré
                "wrapper": {"addresses": [4]},
            }
        ),
        encoding="utf-8",
    )
    groups = load_groups(p)
    assert set(groups) == {"ok_group", "wrapper"}
    g = groups["ok_group"]
    assert isinstance(g, GroupDef)
    assert g.name == "Groupe OK" and g.color == "#FF0000" and g.addresses == [1, 2]
    assert groups["wrapper"].name == "wrapper"  # name par défaut = id


def test_load_groups_accepts_groups_wrapper(tmp_path: Path) -> None:
    p = tmp_path / "groups.json"
    p.write_text(json.dumps({"groups": {"g1": {"addresses": [1]}}}), encoding="utf-8")
    assert set(load_groups(p)) == {"g1"}


# ---------------------------------------------------------------------------
# Setup : groupes chargés, entités + device de groupe créés
# ---------------------------------------------------------------------------


async def test_groups_loaded_and_group_entities_created(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)

    assert set(coord.groups) == {"serre_1_nord"}
    group = coord.groups["serre_1_nord"]
    assert group.name == "Serre 1 — Nord" and group.color == "#4CAF50" and group.area == "serre_1"
    assert group.addresses == [1, 2]

    # entités de groupe : light + select recette + button save
    light_id = _entity_id(hass, LIGHT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_light")
    select_id = _entity_id(
        hass, SELECT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_recipe"
    )
    button_id = _entity_id(hass, "button", entry, f"{entry.entry_id}_group_serre_1_nord_save")
    assert light_id and select_id and button_id

    # device groupe relié au hub
    dreg = dr.async_get(hass)
    hub = dreg.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    gdev = dreg.async_get_device_by_identifier((DOMAIN, "group_serre_1_nord"), entry.entry_id)
    assert gdev is not None
    assert gdev.via_device_id == hub.id
    assert gdev.name == "Serre 1 — Nord"


async def test_no_groups_no_group_entities(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path, groups=None, expected=1)
    assert coord.groups == {}
    assert (
        er.async_get(hass).async_get_entity_id(
            LIGHT_DOMAIN, DOMAIN, f"{entry.entry_id}_group_x_light"
        )
        is None
    )
    assert len(hass.states.async_all("light")) == 1  # seulement le SPOT


# ---------------------------------------------------------------------------
# Labels colorés + area posés sur les devices membres
# ---------------------------------------------------------------------------


async def test_labels_and_area_applied_to_member_devices(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    await coord.async_refresh()  # synchro des registres à chaque polling
    await hass.async_block_till_done()

    lreg = lr.async_get(hass)
    label = lreg.async_get_label_by_name("serre_1_nord")
    assert label is not None
    assert label.color == "#4CAF50"
    assert label.icon == "mdi:leaf"

    areg = ar.async_get(hass)
    area = areg.async_get_area_by_name("serre_1")
    assert area is not None

    dreg = dr.async_get(hass)
    for address in (1, 2):
        spot = dreg.async_get_device_by_identifier((DOMAIN, f"spot_{address}"), entry.entry_id)
        assert spot is not None
        assert label.label_id in spot.labels
        assert spot.area_id == area.id

    # le device du groupe rejoint aussi l'area et porte le label : sa carte
    # (light + select recette + bouton save) apparaît dans la vue de la pièce
    gdev = dreg.async_get_device_by_identifier((DOMAIN, "group_serre_1_nord"), entry.entry_id)
    assert gdev is not None
    assert label.label_id in gdev.labels
    assert gdev.area_id == area.id


async def test_registry_sync_is_additive_and_idempotent(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=1)
    await coord.async_refresh()
    await hass.async_block_till_done()

    dreg = dr.async_get(hass)
    spot = dreg.async_get_device_by_identifier((DOMAIN, "spot_1"), entry.entry_id)
    # l'utilisateur pose un label perso : la synchro ne doit pas le retirer
    lreg = lr.async_get(hass)
    perso = lreg.async_create(name="perso")
    dreg.async_update_device(spot.id, labels=set(spot.labels) | {perso.label_id})

    await coord.async_refresh()
    await hass.async_block_till_done()
    spot = dreg.async_get_device_by_identifier((DOMAIN, "spot_1"), entry.entry_id)
    group_label = lreg.async_get_label_by_name("serre_1_nord")
    assert group_label.label_id in spot.labels
    assert perso.label_id in spot.labels


# ---------------------------------------------------------------------------
# Entité light du groupe
# ---------------------------------------------------------------------------


async def test_group_light_turn_on_brightness_applies_to_all_members(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    light_id = _entity_id(hass, LIGHT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_light")

    await _call(hass, LIGHT_DOMAIN, "turn_on", {"entity_id": light_id, "brightness": 255})

    assert coord.data.spots[1].currents == [2150] * 16
    assert coord.data.spots[2].currents == [2150] * 16
    state = hass.states.get(light_id)
    assert state.state == "on"
    assert state.attributes["brightness"] == 255


async def test_group_light_turn_off_and_default_on(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[800] * 16), 2: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    light_id = _entity_id(hass, LIGHT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_light")

    assert hass.states.get(light_id).state == "on"  # au moins un membre allumé

    await _call(hass, LIGHT_DOMAIN, "turn_off", {"entity_id": light_id})
    assert coord.data.spots[1].currents == [0] * 16
    assert coord.data.spots[2].currents == [0] * 16
    assert hass.states.get(light_id).state == "off"

    # turn_on sans luminosité, aucune recette : 500 mA (DEFAULT_CURRENT_MA, D11) sur tous
    await _call(hass, LIGHT_DOMAIN, "turn_on", {"entity_id": light_id})
    assert coord.data.spots[1].currents == [500] * 16
    assert coord.data.spots[2].currents == [500] * 16


# ---------------------------------------------------------------------------
# Select recette du groupe + service group:<id>
# ---------------------------------------------------------------------------


async def test_group_select_applies_recipe_to_all_members(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    select_id = _entity_id(
        hass, SELECT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_recipe"
    )
    events: list[dict] = []
    hass.bus.async_listen(EVENT_GROUP_RECIPE_APPLIED, lambda e: events.append(e.data))

    # options = fichiers recipes/*.json
    assert hass.states.get(select_id).attributes["options"] == ["croissance.json"]

    await _call(
        hass, SELECT_DOMAIN, "select_option", {"entity_id": select_id, "option": "croissance.json"}
    )

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[2].currents == [800] * 8 + [0] * 8
    # last_recipe mémorisé sur chaque membre + select reflète la recette commune
    assert coord.data.spots[1].last_recipe == "croissance.json"
    assert hass.states.get(select_id).state == "croissance.json"
    # événement récapitulatif de groupe + événements par membre
    assert events[-1]["group"] == "serre_1_nord"
    assert events[-1]["ok"] == 2 and events[-1]["errors"] == 0

    # turn_on sans luminosité réapplique la dernière recette du groupe (D11)
    bus[1].currents = [0] * 16
    bus[2].currents = [0] * 16
    await coord.async_refresh()
    light_id = _entity_id(hass, LIGHT_DOMAIN, entry, f"{entry.entry_id}_group_serre_1_nord_light")
    await _call(hass, LIGHT_DOMAIN, "turn_on", {"entity_id": light_id})
    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8


async def test_service_apply_recipe_group_target(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    recipe_events: list[dict] = []
    hass.bus.async_listen(EVENT_RECIPE_APPLIED, lambda e: recipe_events.append(e.data))

    await _call(
        hass, DOMAIN, "apply_recipe", {"address": "group:serre_1_nord", "recipe": "croissance.json"}
    )

    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert coord.data.spots[2].currents == [800] * 8 + [0] * 8
    assert {e["address"] for e in recipe_events} == {1, 2}
    assert all(e.get("group_id") == "serre_1_nord" for e in recipe_events)


async def test_service_group_unknown_raises(hass, monkeypatch, tmp_path) -> None:
    await _setup(hass, monkeypatch, {1: FakeSpot()}, tmp_path, expected=1)
    with pytest.raises(HomeAssistantError):
        await _call(
            hass,
            DOMAIN,
            "apply_recipe",
            {"address": "group:inexistant", "recipe": "croissance.json"},
        )


async def test_service_recipe_path_traversal_rejected(hass, monkeypatch, tmp_path) -> None:
    await _setup(hass, monkeypatch, {1: FakeSpot()}, tmp_path, expected=1)
    with pytest.raises(HomeAssistantError):
        await _call(hass, DOMAIN, "apply_recipe", {"address": "1", "recipe": "../secrets.json"})
    with pytest.raises(HomeAssistantError):
        await _call(hass, DOMAIN, "apply_scene", {"file": "../../etc/passwd"})


async def test_service_save_and_set_channels_group_target(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[500] * 16), 2: FakeSpot(currents=[500] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    link = FakePhsLink.instances[0]

    await _call(hass, DOMAIN, "save", {"address": "group:serre_1_nord"})
    assert ("WP", 1, "") in link.sent and ("WP", 2, "") in link.sent

    await _call(
        hass,
        DOMAIN,
        "set_channels",
        {"address": "group:serre_1_nord", "currents": "900 " * 15 + "900"},
    )
    assert coord.data.spots[1].currents == [900] * 16
    assert coord.data.spots[2].currents == [900] * 16

    await _call(
        hass, DOMAIN, "set_channel", {"address": "group:serre_1_nord", "channel": 1, "ma": 0}
    )
    assert coord.data.spots[1].currents[0] == 0
    assert coord.data.spots[2].currents[0] == 0


async def test_group_partial_failure_does_not_abort(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[0] * 16), 2: FakeSpot(currents=[0] * 16)}
    _, coord = await _setup(hass, monkeypatch, bus, tmp_path)
    events: list[dict] = []
    hass.bus.async_listen(EVENT_GROUP_RECIPE_APPLIED, lambda e: events.append(e.data))

    bus[2].alive = False  # carte 2 muette
    with pytest.raises(HomeAssistantError):
        await _call(
            hass,
            DOMAIN,
            "apply_recipe",
            {"address": "group:serre_1_nord", "recipe": "croissance.json"},
        )

    # la carte 1 a bien reçu la recette malgré l'échec de la carte 2
    assert coord.data.spots[1].currents == [800] * 8 + [0] * 8
    assert events[-1]["ok"] == 1 and events[-1]["errors"] == 1
    assert events[-1]["results"]["2"] is not None


# ---------------------------------------------------------------------------
# Rechargement à chaud de groups.json
# ---------------------------------------------------------------------------


async def test_groups_hot_reload_adds_entities(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(), 2: FakeSpot(), 3: FakeSpot()}
    entry, coord = await _setup(hass, monkeypatch, bus, tmp_path, expected=3)
    assert set(coord.groups) == {"serre_1_nord"}

    # édition de groups.json : nouveau groupe + changement de couleur
    groups = dict(GROUPS)
    groups["serre_1_nord"]["color"] = "#00FF00"
    groups["serre_2_all"] = {"name": "Serre 2", "addresses": [3]}
    (tmp_path / "phs16lc" / "groups.json").write_text(json.dumps(groups), encoding="utf-8")

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert set(coord.groups) == {"serre_1_nord", "serre_2_all"}
    # nouvelles entités créées sans redémarrage
    assert (
        er.async_get(hass).async_get_entity_id(
            LIGHT_DOMAIN, DOMAIN, f"{entry.entry_id}_group_serre_2_all_light"
        )
        is not None
    )
    # couleur du label mise à jour
    label = lr.async_get(hass).async_get_label_by_name("serre_1_nord")
    assert label.color == "#00FF00"


# ---------------------------------------------------------------------------
# Bouton save du groupe
# ---------------------------------------------------------------------------


async def test_group_save_button_sends_wp_to_all_members(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bus = {1: FakeSpot(currents=[500] * 16), 2: FakeSpot(currents=[500] * 16)}
    entry, _ = await _setup(hass, monkeypatch, bus, tmp_path)
    button_id = _entity_id(hass, "button", entry, f"{entry.entry_id}_group_serre_1_nord_save")

    await _call(hass, "button", "press", {"entity_id": button_id})

    link = FakePhsLink.instances[0]
    assert ("WP", 1, "") in link.sent and ("WP", 2, "") in link.sent


# ---------------------------------------------------------------------------
# Copie auto des données embarquées (recettes/scènes/groups.json)
# ---------------------------------------------------------------------------


def test_install_embedded_data_copies_only_missing(tmp_path: Path) -> None:
    dest = tmp_path / "phs16lc" / "recipes"
    copied = phs16lc._install_embedded_data(dest)
    # 3 recettes + 1 scène + groups.json
    assert copied == 5
    assert (dest / "croissance.json").is_file()
    assert (dest.parent / "scenes" / "serre.json").is_file()
    assert (dest.parent / "groups.json").is_file()

    # idempotent : second passage n'écrit rien
    assert phs16lc._install_embedded_data(dest) == 0

    # un fichier modifié par l'utilisateur n'est jamais écrasé
    custom = dest / "croissance.json"
    custom.write_text('{"name": "ma recette"}', encoding="utf-8")
    assert phs16lc._install_embedded_data(dest) == 0
    assert json.loads(custom.read_text(encoding="utf-8"))["name"] == "ma recette"


async def test_install_embedded_data_skipped_for_custom_dir(hass: HomeAssistant) -> None:
    """Dossier recipes_dir personnalisé = géré manuellement : aucune copie auto."""
    entry = SimpleNamespace(data={"recipes_dir": "/tmp/quelque-chose"}, options={})
    assert await phs16lc.async_install_embedded_data(hass, entry) == 0


async def test_install_embedded_data_oserror_does_not_break_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si la copie auto échoue (OSError, ex. /config non inscriptible en dev Mac),
    le setup de l'entrée doit réussir quand même (warning uniquement)."""

    def boom(recipes_dir):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(phs16lc, "_install_embedded_data", boom)
    entry = SimpleNamespace(data={"recipes_dir": "/config/phs16lc/recipes"}, options={})
    assert await phs16lc.async_install_embedded_data(hass, entry) == 0
