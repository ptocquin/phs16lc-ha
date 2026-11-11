"""Diagnostics HA (Réglages → Système → Réparations → « Télécharger les diagnostics »).

Inclut : config de l'entrée, port série, ports détectés, et par SPOT l'état
courant + identité (@GI) + cartes LED (@GL) quand la carte est en ligne.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_RECIPES_DIR, DOMAIN, entry_value
from .coordinator import Phs16Coordinator
from .phs16ctl import protocol as proto
from .phs16ctl.link import T_GI, T_GL, available_ports


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]

    def _collect() -> dict[str, Any]:
        spots: dict[str, Any] = {}
        for address, spot in sorted(coordinator.data.spots.items()):
            info: dict[str, Any] = {
                "online": spot.online,
                "currents": spot.currents,
                "temperatures": spot.temperatures,
                "last_recipe": spot.last_recipe,
                "last_group": spot.last_group,
            }
            if spot.online:
                resp = coordinator.link.send("GI", address, timeout=T_GI)
                info["identity"] = proto.decode_identity(resp) if resp is not None else None
                resp = coordinator.link.send("GL", address, timeout=T_GL)
                info["led_boards"] = proto.decode_led_boards(resp) if resp is not None else None
            spots[str(address)] = info
        return {"ports_detected": available_ports(), "spots": spots}

    collected = await coordinator.async_io(_collect)
    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "link": {"port": coordinator.link.port},
        "recipes_dir": entry_value(entry, CONF_RECIPES_DIR),
        **collected,
    }
