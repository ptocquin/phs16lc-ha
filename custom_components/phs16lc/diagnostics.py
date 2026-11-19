"""Diagnostics HA (Réglages → Système → Réparations → « Télécharger les diagnostics »).

Inclut : config de l'entrée, port série, ports détectés, et par SPOT l'état
courant + identité (@GI) + cartes LED (@GL) quand la carte est en ligne.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PORT,
    DOMAIN,
    entry_value,
    groups_file_for,
    recipes_dir_for_entry,
    scenes_dir_for,
)
from .coordinator import Phs16Coordinator
from .phs16ctl import protocol as proto
from .phs16ctl.link import T_GI, T_GL, available_ports


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: Phs16Coordinator = hass.data[DOMAIN][entry.entry_id]

    link = coordinator.link  # None si le port est perdu (B2, reconnexion auto)

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
            if spot.online and link is not None:
                resp = link.send("GI", address, timeout=T_GI)
                info["identity"] = proto.decode_identity(resp) if resp is not None else None
                resp = link.send("GL", address, timeout=T_GL)
                info["led_boards"] = proto.decode_led_boards(resp) if resp is not None else None
            spots[str(address)] = info
        return {"ports_detected": available_ports(), "spots": spots}

    collected = await coordinator.async_io(_collect)

    def _fs_info() -> dict[str, Any]:
        recipes_dir = recipes_dir_for_entry(entry)
        scenes_dir = scenes_dir_for(recipes_dir)

        def _count(d: Path) -> int:
            try:
                return len(list(d.glob("*.json"))) if d.is_dir() else 0
            except OSError:
                return 0

        return {
            "recipes_dir": {
                "configured": str(entry.options.get("recipes_dir", entry.data.get("recipes_dir"))),
                "resolved": str(recipes_dir),
                "exists": recipes_dir.is_dir(),
                "recipe_files": _count(recipes_dir),
                "scenes_dir": str(scenes_dir),
                "scene_files": _count(scenes_dir),
            }
        }

    recipes_dir = recipes_dir_for_entry(entry)
    groups_file = groups_file_for(recipes_dir)
    groups_info = {
        group_id: {
            "name": group.name,
            "color": group.color,
            "icon": group.icon,
            "area": group.area,
            "addresses": group.addresses,
            "members_online": [
                a
                for a in group.addresses
                if (spot := coordinator.data.spots.get(a)) is not None and spot.online
            ],
            "registry": coordinator.group_registry_sync.get(group_id),
        }
        for group_id, group in sorted(coordinator.groups.items())
    }

    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "link": (
            {
                "port": link.port,
                "tx_port": link.tx_port,
                "rx_port": link.rx_port,
                "single_port": link.single_port,
                "connected": True,
            }
            if link is not None
            else {
                "port": str(entry_value(entry, CONF_PORT)),
                "connected": False,
                "error": "port perdu — reconnexion automatique en cours (B2)",
            }
        ),
        "groups_file": {
            "path": str(groups_file),
            "exists": groups_file.is_file(),
            "groups": groups_info,
        },
        **_fs_info(),
        **collected,
    }
