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


@dataclass
class SyncResult:
    """Résultat de la synchro des registres : récap (diagnostics) + indicateur dirty."""

    recap: dict[str, Any]
    dirty: bool  # True si `state` a été modifié -> à persister


def load_sync_state(path: Path) -> dict[str, Any]:
    """Charge l'état persisté de la synchro (labels/areas appliqués). Absent/illisible → {}."""
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except OSError, ValueError:
        pass
    return {}


def save_sync_state(path: Path, state: dict[str, Any]) -> None:
    """Persiste l'état de la synchro (écriture atomique). Exécuté en executor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(path)


@callback
def sync_group_registries(
    hass: HomeAssistant, entry, groups: dict[str, GroupDef], state: dict[str, Any]
) -> SyncResult:
    """Pose label coloré + area sur les devices SPOT membres de chaque groupe **et
    sur le device du groupe lui-même** (pour que sa carte — lampe, liste
    « Recette », bouton NVM — apparaisse dans la vue de la pièce).

    **Règle anti-conflit** (bugfix : la synchro tournait à chaque polling et
    écrasait les modifications manuelles de l'UI) : une valeur n'est (re)écrite
    que si elle est **inchangée depuis notre dernier apply** (enregistré dans
    `state`, persisté dans `.groups_sync_state.json`) ou si elle est **vide**.
    Toute valeur modifiée manuellement dans l'UI (pièce, étiquette, couleur) est
    respectée et n'est jamais réécrite. On ne retire jamais rien (additif).

    `state` est muté ; appeler sur le event loop. Retourne le récap + dirty.
    """
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import label_registry as lr

    lreg = lr.async_get(hass)
    areg = ar.async_get(hass)
    dreg = dr.async_get(hass)

    recap: dict[str, Any] = {}
    dirty = False
    for gid, group in groups.items():
        # --- label du groupe ---
        lkey = f"label:{gid}"
        rec = state.get(lkey)
        label = lreg.async_get_label(rec.get("label_id")) if rec else None
        if label is None:
            label = lreg.async_get_label_by_name(gid)
        if label is None:
            label = lreg.async_create(name=gid, color=group.color, icon=group.icon)
            state[lkey] = {"label_id": label.label_id, "color": label.color, "icon": label.icon}
            dirty = True
        elif rec is None:
            # label préexistant (ex. upgrade) : on enregistre tel quel, sans modifier
            state[lkey] = {
                "label_id": label.label_id,
                "color": label.color,
                "icon": label.icon,
                "user": True,  # posé hors de notre synchro -> on ne touchera plus sa couleur
            }
            dirty = True
        elif (
            not rec.get("user")
            and rec.get("color") == label.color
            and rec.get("icon") == label.icon
        ):
            # inchangé depuis notre apply -> on propage le (nouveau) groups.json
            updates: dict[str, Any] = {}
            if group.color is not None and label.color != group.color:
                updates["color"] = group.color
            if group.icon is not None and label.icon != group.icon:
                updates["icon"] = group.icon
            if updates:
                label = lreg.async_update(label.label_id, **updates)
                state[lkey] = {"label_id": label.label_id, "color": label.color, "icon": label.icon}
                dirty = True
        # else : label modifié manuellement (couleur/icône) -> respecté

        # --- area ---
        area_id: str | None = None
        if group.area:
            area = areg.async_get_area_by_name(group.area)
            if area is None:
                area = areg.async_create(name=group.area)
            area_id = area.id

        # --- devices : SPOT membres + device du groupe ---
        targets = [(f"spot_{a}", a) for a in group.addresses] + [(f"group_{gid}", None)]
        touched: list[str] = []
        for ident, _addr in targets:
            dev = dreg.async_get_device_by_identifier((DOMAIN, ident), entry.entry_id)
            if dev is None:
                continue  # device pas encore créé (carte pas encore découverte)
            dkey = f"device:{dev.id}"
            rec = state.get(dkey)
            cur_labels, cur_area = set(dev.labels), dev.area_id
            if rec is None:
                # première observation : on remplit les blancs (label manquant,
                # area vide) et on enregistre l'état — sans jamais écraser une
                # valeur préexistante posée manuellement
                kwargs: dict[str, Any] = {}
                new_labels = cur_labels | {label.label_id}
                if new_labels != cur_labels:
                    kwargs["labels"] = new_labels
                new_area = cur_area
                area_user = cur_area is not None
                if area_id is not None and cur_area is None:
                    kwargs["area_id"] = area_id
                    new_area = area_id
                    area_user = False
                if kwargs:
                    dreg.async_update_device(dev.id, **kwargs)
                    touched.append(ident)
                state[dkey] = {
                    "labels": sorted(new_labels),
                    "area_id": new_area,
                    "area_user": area_user,  # area préexistante = posée par l'utilisateur
                }
                dirty = True
            else:
                rec_labels = set(rec.get("labels") or [])
                rec_area = rec.get("area_id")
                if rec_labels == cur_labels and rec_area == cur_area:
                    # inchangé depuis notre apply -> on propage le nouveau groups.json
                    kwargs = {}
                    new_labels = cur_labels | {label.label_id}
                    if new_labels != cur_labels:
                        kwargs["labels"] = new_labels
                    new_area = cur_area
                    if area_id is not None and cur_area != area_id and not rec.get("area_user"):
                        kwargs["area_id"] = area_id
                        new_area = area_id
                    if kwargs:
                        dreg.async_update_device(dev.id, **kwargs)
                        touched.append(ident)
                        state[dkey] = {"labels": sorted(new_labels), "area_id": new_area}
                        dirty = True
                # else : device modifié manuellement dans l'UI -> respecté, non réécrit

        recap[gid] = {
            "name": group.name,
            "label_id": label.label_id,
            "label_color": label.color,
            "area_id": area_id,
            "devices_updated": touched,
        }
    return SyncResult(recap=recap, dirty=dirty)
