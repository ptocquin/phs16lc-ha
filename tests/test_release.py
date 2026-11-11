"""Tests du packaging de release et du script de déploiement (phase 9, stdlib seul)."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from package_release import build_zip, release_files


def test_release_zip_layout(root_dir: Path, tmp_path: Path) -> None:
    """Le zip a le layout racine HACS/Marketplace et embarque tout le composant."""
    zip_path = build_zip(tmp_path)
    manifest = json.loads(
        (root_dir / "custom_components" / "phs16lc" / "manifest.json").read_text("utf-8")
    )
    assert zip_path.name == f"phs16lc-{manifest['version']}.zip"

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    # racine attendue par HACS/Marketplace
    assert "hacs.json" in names
    assert "README.md" in names
    assert "brand/icon.png" in names
    assert "custom_components/phs16lc/manifest.json" in names
    # tout le code du composant est embarqué (y compris le vendored phs16ctl)
    component = root_dir / "custom_components" / "phs16lc"
    expected = {
        p.relative_to(root_dir).as_posix()
        for p in component.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    assert expected <= names
    assert any(n.startswith("custom_components/phs16lc/phs16ctl/") for n in names)
    # aucun artefact d'exécution
    assert not any("__pycache__" in n or n.endswith((".pyc", ".pyo")) for n in names)


def test_release_files_are_under_root(root_dir: Path) -> None:
    for path in release_files():
        assert path.is_relative_to(root_dir)
        assert path.is_file()


def test_deploy_script_targets_custom_components(root_dir: Path) -> None:
    script = (root_dir / "tools" / "deploy_to_linux.sh").read_text("utf-8")
    assert script.startswith("#!/bin/sh")
    assert "custom_components" in script
    assert "ssh" in script and "tar" in script
