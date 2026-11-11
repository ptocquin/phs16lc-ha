"""Configuration pytest de ha-integration.

Le plugin officiel `pytest-homeassistant` (>= 2026.11) se charge automatiquement
via son entry point pytest11 ; sa fixture `hass` active les custom integrations
par défaut. Les phases 0 (tests stdlib) n'utilisent aucune fixture HA.
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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Charge les intégrations présentes dans ./custom_components (ha-integration/)."""
    yield
