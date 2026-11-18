"""Vérifie que la copie vendored de phs16ctl est synchronisée avec la source."""

from __future__ import annotations

from pathlib import Path

MODULES = ["__init__.py", "protocol.py", "link.py", "controller.py", "profiles.py"]


def _src(root: Path) -> Path:
    return root.parent / "phs16ctl" / "src" / "phs16ctl"


def _dst(root: Path) -> Path:
    return root / "custom_components" / "phs16lc" / "phs16ctl"


def test_vendored_modules_exist_and_match(root_dir: Path) -> None:
    for name in MODULES:
        src = _src(root_dir) / name
        dst = _dst(root_dir) / name
        assert dst.is_file(), f"{name} absent de la copie vendored (lancer tools/sync_phs16ctl.py)"
        assert dst.read_bytes() == src.read_bytes(), (
            f"{name} désynchronisé (lancer tools/sync_phs16ctl.py)"
        )


def test_cli_not_vendored(root_dir: Path) -> None:
    assert not (_dst(root_dir) / "cli.py").exists(), (
        "cli.py ne doit pas être vendored (spécifique CLI)"
    )


def test_embedded_recipes_scenes_match_phs16ctl(root_dir: Path) -> None:
    """Les recettes/scènes embarquées (copiées vers <config>/phs16lc/ au boot)
    doivent rester synchronisées avec phs16ctl/{recipes,scenes}."""
    for name in ("recipes", "scenes"):
        src_dir = root_dir.parent / "phs16ctl" / name
        dst_dir = root_dir / "custom_components" / "phs16lc" / name
        src_files = {p.name: p.read_bytes() for p in src_dir.glob("*.json")}
        dst_files = {p.name: p.read_bytes() for p in dst_dir.glob("*.json")}
        assert src_files, f"aucune source dans {src_dir}"
        assert dst_files == src_files, (
            f"{name}/ embarqué désynchronisé (lancer tools/sync_phs16ctl.py)"
        )


def test_embedded_groups_json_present(root_dir: Path) -> None:
    """Un groups.json d'exemple est embarqué (copié vers <config>/phs16lc/ au boot)."""
    import json

    path = root_dir / "custom_components" / "phs16lc" / "groups.json"
    assert path.is_file(), "groups.json embarqué absent"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    for gid, g in data.items():
        assert g.get("addresses"), f"groupe {gid} sans adresses"


def test_vendored_controller_importable_shape(root_dir: Path) -> None:
    """La copie vendored expose bien les API métier attendues (contrat avec phs16ctl)."""
    import ast

    tree = ast.parse((_dst(root_dir) / "controller.py").read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert {"Luminaire", "Recipe", "Scene", "apply_scene", "scan_line", "scan_table"} <= names
