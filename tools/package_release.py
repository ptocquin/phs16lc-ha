#!/usr/bin/env python3
"""Construit le zip de distribution de l'intégration (layout racine HACS/Marketplace).

Usage :

    python3 tools/package_release.py [--dest dist]

Produit `dist/phs16lc-<version>.zip` (version lue dans manifest.json) avec :

    hacs.json
    README.md
    brand/icon.png, brand/logo.png
    custom_components/phs16lc/**   (sans __pycache__ ni *.pyc)

C'est exactement la racine attendue d'un dépôt HACS/Marketplace : le zip sert
de pièce jointe de release sur GitLab, le dépôt sert de source « custom repo ».
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "phs16lc"
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
TOP_FILES = ("hacs.json", "README.md")


def release_files() -> list[Path]:
    """Fichiers à embarquer, chemins relatifs à la racine du dépôt ha-integration/."""
    files = [ROOT / name for name in TOP_FILES if (ROOT / name).is_file()]
    brand = ROOT / "brand"
    if brand.is_dir():
        files += sorted(p for p in brand.iterdir() if p.is_file())
    files += sorted(
        p
        for p in COMPONENT.rglob("*")
        if p.is_file()
        and not any(part in EXCLUDE_DIRS for part in p.parts)
        and p.suffix not in EXCLUDE_SUFFIXES
    )
    return files


def build_zip(dest: Path) -> Path:
    """Écrit le zip de release dans `dest` et retourne son chemin."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / f"phs16lc-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in release_files():
            zf.write(path, path.relative_to(ROOT).as_posix())
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=ROOT / "dist", help="dossier de sortie")
    args = parser.parse_args(argv)
    zip_path = build_zip(args.dest)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    print(f"{zip_path} ({zip_path.stat().st_size} octets, {len(names)} fichiers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
