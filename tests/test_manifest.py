"""Validation du packaging de l'intégration (phase 0, sans runtime HA).

Règles hassfest 2026.11 vérifiées ici :
- clés requises du manifest (domain, name, version, documentation, issue_tracker, codeowners) ;
- PAS de clé `homeassistant` dans manifest.json (version min -> hacs.json) ;
- `requirements` épinglé comme HA core (pyserial==3.5 dans package_constraints 2026.11) ;
- `hacs.json` présent avec la clé `homeassistant` ;
- brand/icon.png présent et PNG valide.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

REQUIRED_MANIFEST_KEYS = {"domain", "name", "version", "documentation", "issue_tracker", "codeowners"}
VALID_IOT_CLASSES = {"assumed_state", "calculated", "cloud_polling", "cloud_push", "local_polling", "local_push"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_required_keys(root_dir: Path) -> None:
    manifest = _load(root_dir / "custom_components" / "phs16lc" / "manifest.json")
    assert manifest["domain"] == "phs16lc"
    assert REQUIRED_MANIFEST_KEYS <= set(manifest), f"clés manquantes: {REQUIRED_MANIFEST_KEYS - set(manifest)}"


def test_manifest_no_homeassistant_key(root_dir: Path) -> None:
    """hassfest 2026.11 rejette la clé `homeassistant` dans le manifest des custom integrations."""
    manifest = _load(root_dir / "custom_components" / "phs16lc" / "manifest.json")
    assert "homeassistant" not in manifest


def test_manifest_shape(root_dir: Path) -> None:
    manifest = _load(root_dir / "custom_components" / "phs16lc" / "manifest.json")
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "hub"
    assert manifest["iot_class"] in VALID_IOT_CLASSES
    assert manifest["requirements"] == ["pyserial==3.5"]  # pin identique à HA core 2026.11
    usb = manifest["usb"]
    assert any(u["vid"] == "0403" and u["pid"] == "6001" for u in usb), "matcher USB FTDI 0403:6001 attendu"
    assert manifest["version"].count(".") == 2


def test_hacs_json(root_dir: Path) -> None:
    hacs = _load(root_dir / "hacs.json")
    assert hacs["name"]
    assert hacs["homeassistant"] == "2026.11.0"  # version min HA pour le Marketplace


def test_brand_icon_is_valid_png(root_dir: Path) -> None:
    icon = root_dir / "brand" / "icon.png"
    assert icon.is_file(), "brand/icon.png requis par le Marketplace"
    data = icon.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR : largeur/hauteur
    (w, h) = struct.unpack(">II", data[16:24])
    assert w == h >= 256, f"icon carré attendu, reçu {w}x{h}"


def test_translations_parse(root_dir: Path) -> None:
    integ = root_dir / "custom_components" / "phs16lc"
    strings = _load(integ / "strings.json")
    for lang in ("en", "fr"):
        tr = _load(integ / "translations" / f"{lang}.json")
        assert tr["config"]["step"]["user"]["data"].keys() == strings["config"]["step"]["user"]["data"].keys()
        assert tr["services"].keys() == strings["services"].keys()


def test_services_yaml_fields_match_strings(root_dir: Path) -> None:
    import yaml  # pyyaml installé avec homeassistant ; fallback mini-parse sinon

    integ = root_dir / "custom_components" / "phs16lc"
    services = yaml.safe_load((integ / "services.yaml").read_text(encoding="utf-8"))
    strings = _load(integ / "strings.json")
    assert set(services) == set(strings["services"]), "services.yaml et strings.json désynchronisés"
    for name, spec in services.items():
        fields = set((spec.get("fields") or {}).keys())
        assert fields == set(strings["services"][name].get("fields", {}).keys()), name
