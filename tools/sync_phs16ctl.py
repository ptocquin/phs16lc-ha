#!/usr/bin/env python3
"""Synchronise la copie vendored de `phs16ctl` dans l'intégration Home Assistant.

Usage :
    python3 tools/sync_phs16ctl.py          # depuis n'importe où
    python3 ha-integration/tools/sync_phs16ctl.py   # depuis la racine du dépôt

Copie les modules métier de `phs16ctl/src/phs16ctl/` vers
`custom_components/phs16lc/phs16ctl/` :

    __init__.py, protocol.py, link.py, controller.py, profiles.py

et les données embarquées (recettes + scènes, copiées au premier démarrage de
l'intégration vers `<config>/phs16lc/`) :

    phs16ctl/recipes/*.json  -> custom_components/phs16lc/recipes/
    phs16ctl/scenes/*.json   -> custom_components/phs16lc/scenes/

`cli.py` est volontairement exclu (spécifique à la ligne de commande).
`groups.json` n'est PAS synchronisé : c'est un fichier spécifique à
l'intégration (exemple embarqué, édité ensuite dans `<config>/phs16lc/`).
La source de vérité reste `phs16ctl/` : ne jamais éditer la copie vendored,
modifier `phs16ctl/` puis relancer ce script.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "phs16ctl" / "src" / "phs16ctl"
DST = ROOT / "custom_components" / "phs16lc" / "phs16ctl"
COMPONENT = ROOT / "custom_components" / "phs16lc"

MODULES = ["__init__.py", "protocol.py", "link.py", "controller.py", "profiles.py"]
DATA_DIRS = ("recipes", "scenes")  # copiés depuis phs16ctl/<dir>/ vers phs16lc/<dir>/


def main() -> int:
    missing = [m for m in MODULES if not (SRC / m).is_file()]
    if missing:
        print(f"ERREUR: modules introuvables dans {SRC}: {missing}", file=sys.stderr)
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    for name in MODULES:
        shutil.copy2(SRC / name, DST / name)
        print(f"  {name}  ->  {DST.relative_to(ROOT)}/")
    for pyc in (DST / "__pycache__").glob("*"):
        pyc.unlink()
    copied = 0
    for name in DATA_DIRS:
        src_dir = ROOT.parent / "phs16ctl" / name
        dst_dir = COMPONENT / name
        if not src_dir.is_dir():
            print(f"ERREUR: dossier introuvable : {src_dir}", file=sys.stderr)
            return 1
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.glob("*.json")):
            shutil.copy2(src, dst_dir / src.name)
            copied += 1
            print(f"  {name}/{src.name}  ->  {dst_dir.relative_to(ROOT)}/")
    print(
        f"OK: {len(MODULES)} modules + {copied} fichiers de données synchronisés "
        f"({SRC.name}/ -> phs16ctl/ vendored, phs16ctl/{{recipes,scenes}}/ -> embarqués)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
