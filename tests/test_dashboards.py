"""Tests du générateur de dashboards : groupes natifs v1.3.0 dans la vue chambre."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def _gen(root_dir: Path):
    sys.path.insert(0, str(root_dir / "dashboards"))
    import generate_dashboards as gd

    chambres = gd.load_chambres(
        root_dir / "dashboards" / "mapping.yaml", root_dir / "dashboards" / "groups.json"
    )
    return gd, chambres


def test_groups_json_drives_groupes_and_meta(root_dir: Path) -> None:
    _gd, chambres = _gen(root_dir)
    assert set(chambres["serre_1"]["groupes"]) == {"nord", "sud"}
    meta = chambres["serre_1"]["_groups_meta"]["nord"]
    assert meta["name"] == "Serre 1 — Nord"
    assert meta["color"] == "#4CAF50"


def test_dashboard_chambre_has_inline_group_controls(root_dir: Path) -> None:
    """La vue chambre embarque les entités natives du groupe (pas de modal) :
    tile light du groupe + carte entities (select recette, bouton NVM, membres)."""
    gd, chambres = _gen(root_dir)
    dash = gd.gen_dashboard(chambres)
    blob = yaml.safe_dump(dash)
    # entité du groupe natif (device « Serre 1 — Nord » -> slug serre_1_nord)
    assert "light.serre_1_nord" in blob
    assert "select.serre_1_nord_recipe" in blob
    assert "button.serre_1_nord_save_to_nvm" in blob
    # membres du groupe listés inline
    for spot in ("light.spot_1", "light.spot_4"):
        assert spot in blob
    # la vue serre_1 existe et contient une carte entities avec le select recette
    vue = next(v for v in dash["views"] if v["path"] == "serre_1")
    cards = [c for s in vue["sections"] for c in s["cards"]]
    entities_cards = [c for c in cards if c["type"] == "entities"]
    assert entities_cards, "aucune carte entities dans la vue chambre"
    flat = [e if isinstance(e, str) else e["entity"] for c in entities_cards for e in c["entities"]]
    assert "select.serre_1_nord_recipe" in flat
    tiles = [c for c in cards if c["type"] == "tile"]
    assert any(c["entity"] == "light.serre_1_nord" for c in tiles)


def test_dashboard_yaml_is_valid(root_dir: Path, tmp_path: Path) -> None:
    """Le générateur complet produit des YAML valides (dashboard + groups + …)."""
    gd, chambres = _gen(root_dir)
    for doc in (
        gd.gen_dashboard(chambres),
        gd.gen_groups(chambres),
        gd.gen_templates(chambres),
        gd.gen_alert_automations(chambres),
    ):
        yaml.safe_dump(doc)  # lève si non sérialisable
    assert (root_dir / "dashboards" / "groups.json").is_file()
