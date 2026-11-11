#!/usr/bin/env python3
"""Synchronise la copie vendored de `phs16ctl` dans l'intégration Home Assistant.

Usage :
    python3 tools/sync_phs16ctl.py          # depuis n'importe où
    python3 ha-integration/tools/sync_phs16ctl.py   # depuis la racine du dépôt

Copie les modules métier de `phs16ctl/src/phs16ctl/` vers
`custom_components/phs16lc/phs16ctl/` :

    __init__.py, protocol.py, link.py, controller.py, profiles.py

`cli.py` est volontairement exclu (spécifique à la ligne de commande).
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

MODULES = ["__init__.py", "protocol.py", "link.py", "controller.py", "profiles.py"]


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
    print(f"OK: {len(MODULES)} modules synchronisés ({SRC.name}/ -> phs16ctl/ vendored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
