"""Configuration pytest de ha-integration.

Phase 0 : tests purement stdlib (manifest, hacs.json, synchro vendored) —
aucune fixture Home Assistant requise. Les phases suivantes ajouteront les
fixtures `pytest-homeassistant` (hass, enable_custom_integrations) ici.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / "phs16lc"


@pytest.fixture(scope="session")
def root_dir() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def integration_dir() -> Path:
    return INTEGRATION
