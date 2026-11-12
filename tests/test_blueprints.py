"""Tests de l'installation des blueprints embarqués vers /config/blueprints/automation/phs16lc/."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

import custom_components.phs16lc as phs16lc
from custom_components.phs16lc.const import DOMAIN

from .fake_bus import FakeSpot
from .test_init import _setup


def test_install_blueprints_copie_les_fichiers(tmp_path: Path) -> None:
    src = phs16lc.BLUEPRINTS_SRC_DIR
    fichiers = sorted(src.rglob("*.yaml"))
    assert fichiers, "aucun blueprint embarqué trouvé dans custom_components/phs16lc/blueprints/"
    assert phs16lc._install_blueprints(tmp_path) == len(fichiers)
    for f in fichiers:
        dest = tmp_path / f.relative_to(src)
        assert dest.read_text(encoding="utf-8") == f.read_text(encoding="utf-8")
    # idempotent : second passage ne réécrit rien
    assert phs16lc._install_blueprints(tmp_path) == 0


async def test_blueprints_visibles_apres_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _setup(hass, monkeypatch, {1: FakeSpot(1)})
    dest_root = Path(hass.config.path("blueprints", "automation", DOMAIN))
    assert dest_root.is_dir()
    for f in phs16lc.BLUEPRINTS_SRC_DIR.rglob("*.yaml"):
        assert (dest_root / f.relative_to(phs16lc.BLUEPRINTS_SRC_DIR)).exists()
