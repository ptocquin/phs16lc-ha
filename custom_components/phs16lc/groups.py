"""Groupes de luminaires (phase 10) : définition, chargement et visibilité UI.

Un groupe = un ensemble de cartes SPOT (ex. une rangée d'une serre) défini dans
`<config>/phs16lc/groups.json` (à côté de `recipes/`) :

```json
{
  "serre_1_nord": {
    "name": "Serre 1 — Nord",
    "color": "#4CAF50",
    "icon": "mdi:leaf",
    "area": "serre_1",
    "addresses": [1, 2, 3, 4]
  }
}
```

- `color`/`icon` alimentent un **label HA** posé sur chaque device SPOT membre
  (`LabelEntry.color` existe en HA 2026.11) → badge coloré natif sur la carte de
  chaque luminaire du groupe (D21).
- `area` (optionnel) crée l'area si absente et la pose (`area_id`) sur les devices
  membres → regroupement par pièce dans l'UI.

La synchro des registres est **additive** : on ne retire jamais un label/area
posé manuellement dans l'UI. Le fichier est rechargé à chaque cycle de polling :
aucun redémarrage nécessaire (D20).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_GROUP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class GroupDef:
    """Définition d'un groupe de luminaires (entrée de groups.json)."""

    id: str
    name: str
    addresses: list[int] = field(default_factory=list)
    color: str | None = None
    icon: str | None = None
    area: str | None = None


def load_groups(path: Path) -> dict[str, GroupDef]:
    """Charge groups.json. Fichier absent/invalide → {} (avec warning si illisible)."""
    try:
        if not path.is_file():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _LOGGER.warning("groups.json illisible (%s) : %s — aucun groupe chargé", path, exc)
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("groups"), dict):
        raw = raw["groups"]  # accepte aussi {"groups": {...}}
    if not isinstance(raw, dict):
        _LOGGER.warning("groups.json (%s) : objet attendu à la racine — aucun groupe chargé", path)
        return {}
    groups: dict[str, GroupDef] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _GROUP_ID_RE.match(key):
            _LOGGER.warning("groups.json : identifiant de groupe invalide ignoré : %r", key)
            continue
        if not isinstance(value, dict):
            _LOGGER.warning("groups.json : groupe %r invalide (objet attendu) — ignoré", key)
            continue
        addresses = value.get("addresses") or []
        try:
            addrs = [int(a) for a in addresses]
        except TypeError, ValueError:
            _LOGGER.warning("groups.json : adresses invalides pour %r — ignoré", key)
            continue
        if not addrs:
            _LOGGER.warning("groups.json : groupe %r sans adresse — ignoré", key)
            continue
        name = str(value.get("name") or key)
        color = value.get("color")
        icon = value.get("icon")
        area = value.get("area")
        groups[key] = GroupDef(
            id=key,
            name=name,
            addresses=addrs,
            color=str(color) if color else None,
            icon=str(icon) if icon else None,
            area=str(area) if area else None,
        )
    return groups


@callback
def sync_group_registries(
    hass: HomeAssistant, entry, groups: dict[str, GroupDef]
) -> dict[str, Any]:
    """Pose label coloré + area sur les devices SPOT membres de chaque groupe **et
    sur le device du groupe lui-même** (pour que sa carte — lampe, liste
    « Recette », bouton NVM — apparaisse dans la vue de la pièce).

    Additif : ne retire jamais rien. Retourne un récap {groupe: {label_id, area_id,
    devices}} (utilisé par les diagnostics). À appeler sur le event loop.
    """
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import label_registry as lr

    lreg = lr.async_get(hass)
    areg = ar.async_get(hass)
    dreg = dr.async_get(hass)

    recap: dict[str, Any] = {}
    for gid, group in groups.items():
        label = lreg.async_get_label_by_name(gid)
        if label is None:
            label = lreg.async_create(name=gid, color=group.color, icon=group.icon)
        else:
            updates: dict[str, Any] = {}
            if group.color is not None and label.color != group.color:
                updates["color"] = group.color
            if group.icon is not None and label.icon != group.icon:
                updates["icon"] = group.icon
            if updates:
                label = lreg.async_update(label.label_id, **updates)

        area_id: str | None = None
        if group.area:
            area = areg.async_get_area_by_name(group.area)
            if area is None:
                area = areg.async_create(name=group.area)
            area_id = area.id

        touched: list[int] = []
        for address in group.addresses:
            device = dreg.async_get_device_by_identifier(
                (DOMAIN, f"spot_{address}"), entry.entry_id
            )
            if device is None:
                continue  # carte pas encore découverte (rescan)
            labels = set(device.labels) | {label.label_id}
            kwargs: dict[str, Any] = {}
            if labels != set(device.labels):
                kwargs["labels"] = labels
            if area_id is not None and device.area_id != area_id:
                kwargs["area_id"] = area_id
            if kwargs:
                dreg.async_update_device(device.id, **kwargs)
                touched.append(address)

        # le device du groupe rejoint l'area et porte le label : dans la vue de la
        # pièce, sa carte (light + select recette + bouton save) est directement visible
        group_device_updated = False
        gdev = dreg.async_get_device_by_identifier((DOMAIN, f"group_{gid}"), entry.entry_id)
        if gdev is not None:
            kwargs = {}
            labels = set(gdev.labels) | {label.label_id}
            if labels != set(gdev.labels):
                kwargs["labels"] = labels
            if area_id is not None and gdev.area_id != area_id:
                kwargs["area_id"] = area_id
            if kwargs:
                dreg.async_update_device(gdev.id, **kwargs)
                group_device_updated = True

        recap[gid] = {
            "name": group.name,
            "label_id": label.label_id,
            "label_color": label.color,
            "area_id": area_id,
            "group_device_updated": group_device_updated,
            "devices_updated": touched,
        }
    return recap
