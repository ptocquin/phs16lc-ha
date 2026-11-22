"""Handlers des services `phs16lc.*` (décrits dans services.yaml + traductions).

`address` accepte un numéro de carte ("1"), "all" (toutes les cartes connues
du coordinator) ou "group:<id>" (groupe de luminaires de groups.json).

`set_group` / `remove_group` créent, modifient (membres, nom, couleur, icône,
pièce, renommage) et suppriment les groupes de luminaires **depuis l'UI**
(Outils de développement → Actions) : ils réécrivent `<config>/phs16lc/groups.json`
et le coordinator recharge le fichier à chaud (entités de groupe ajoutées/retirées
immédiatement, sans attendre le polling).

Enregistrement idempotent (plusieurs entrées = plusieurs bus) ; les services sont
retirés quand la dernière entrée est déchargée.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import CONF_PORT, DOMAIN, entry_value, groups_file_for, recipes_dir_for_entry
from .coordinator import Phs16Coordinator
from .groups import GROUP_ID_RE, GroupDef, load_groups, save_groups
from .phs16ctl.controller import LuminaireError

SERVICES = (
    "scan",
    "apply_recipe",
    "apply_scene",
    "save",
    "save_recipe",
    "set_channels",
    "set_channel",
    "set_group",
    "remove_group",
)

_ERRORS = (LuminaireError, OSError, ValueError, KeyError)


def _coordinators(hass: HomeAssistant) -> list[Phs16Coordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _group_target(raw: object) -> str | None:
    """ "group:<id>" -> "<id>" ; sinon None (cible = adresse carte)."""
    text = str(raw).strip()
    if text.lower().startswith("group:"):
        return text[len("group:") :].strip()
    return None


def _require_group(coordinator: Phs16Coordinator, group_id: str) -> None:
    if group_id not in coordinator.groups:
        raise ServiceValidationError(
            f"groupe inconnu : {group_id!r} — définis dans <config>/phs16lc/groups.json "
            f"(groupes connus : {sorted(coordinator.groups) or 'aucun'})"
        )


def _raise_if_group_errors(group_id: str, results: dict[int, str | None]) -> None:
    errors = {a: e for a, e in results.items() if e}
    if errors:
        raise HomeAssistantError(f"Groupe {group_id} : {len(errors)} carte(s) en erreur : {errors}")


def _safe_filename(name: str) -> str:
    """Nom de fichier de recette/scène : basename uniquement (pas de chemin)."""
    if not name or Path(name).name != name or name in (".", ".."):
        raise ServiceValidationError(f"nom de fichier invalide : {name!r} (basename attendu)")
    return name


def _addresses(raw: object, coordinator: Phs16Coordinator) -> list[int]:
    """ "1" -> [1] ; "all" -> toutes les adresses connues ; sinon ServiceValidationError."""
    text = str(raw).strip()
    if text.lower() == "all":
        return sorted(coordinator.data.spots)
    try:
        address = int(text)
    except ValueError:
        raise ServiceValidationError(
            f"address invalide : {raw!r} (entier, 'all' ou 'group:<id>')"
        ) from None
    if address not in coordinator.data.spots:
        port = coordinator.entry.data.get("port")
        raise ServiceValidationError(
            f"SPOT {address} inconnu sur {port} — faites d'abord phs16lc.scan"
        )
    return [address]


def _parse_currents(raw: object) -> list[int]:
    """Accepte une liste [800, 0, ...] ou une chaîne "800 0 ..." / "800,0,..."."""
    values = list(raw) if isinstance(raw, (list, tuple)) else str(raw).replace(",", " ").split()
    try:
        currents = [int(v) for v in values]
    except TypeError, ValueError:
        raise ServiceValidationError(f"currents invalides : {raw!r} (liste d'entiers mA)") from None
    if not currents:
        raise ServiceValidationError("currents vide")
    return currents


async def _handle_scan(call: ServiceCall) -> None:
    for coordinator in _coordinators(call.hass):
        await coordinator.async_rescan()


async def _handle_apply_recipe(call: ServiceCall) -> None:
    recipe = _safe_filename(str(call.data["recipe"]))
    group = call.data.get("group") or None
    for coordinator in _coordinators(call.hass):
        gid = _group_target(call.data["address"])
        if gid is not None:
            _require_group(coordinator, gid)
            try:
                results = await coordinator.async_apply_recipe_to_group(gid, recipe, group=group)
            except _ERRORS as exc:
                raise HomeAssistantError(f"Groupe {gid} : {exc}") from exc
            _raise_if_group_errors(gid, results)
            continue
        for address in _addresses(call.data["address"], coordinator):
            try:
                await coordinator.async_apply_recipe(address, recipe, group=group)
            except _ERRORS as exc:
                raise HomeAssistantError(f"SPOT {address} : {exc}") from exc


async def _handle_apply_scene(call: ServiceCall) -> None:
    scene_name = _safe_filename(str(call.data["file"]))
    save = bool(call.data.get("save", False))
    for coordinator in _coordinators(call.hass):
        try:
            await coordinator.async_apply_scene(scene_name, save=save)
        except _ERRORS as exc:
            raise HomeAssistantError(f"Scène {scene_name!r} : {exc}") from exc


async def _handle_save(call: ServiceCall) -> None:
    for coordinator in _coordinators(call.hass):
        gid = _group_target(call.data["address"])
        if gid is not None:
            _require_group(coordinator, gid)
            try:
                results = await coordinator.async_save_group(gid)
            except _ERRORS as exc:
                raise HomeAssistantError(f"Groupe {gid} : {exc}") from exc
            _raise_if_group_errors(gid, results)
            continue
        for address in _addresses(call.data["address"], coordinator):
            try:
                await coordinator.async_save(address)
            except _ERRORS as exc:
                raise HomeAssistantError(f"SPOT {address} : {exc}") from exc


async def _handle_set_channels(call: ServiceCall) -> None:
    currents = _parse_currents(call.data["currents"])
    for coordinator in _coordinators(call.hass):
        gid = _group_target(call.data["address"])
        if gid is not None:
            _require_group(coordinator, gid)
            try:
                results = await coordinator.async_set_channels_group(gid, currents)
            except _ERRORS as exc:
                raise HomeAssistantError(f"Groupe {gid} : {exc}") from exc
            _raise_if_group_errors(gid, results)
            continue
        for address in _addresses(call.data["address"], coordinator):
            spot = coordinator.data.spots[address]
            if spot.currents and len(currents) != len(spot.currents):
                n_card = len(spot.currents)
                raise ServiceValidationError(
                    f"SPOT {address} a {n_card} canaux, {len(currents)} valeurs fournies"
                )
            try:
                await coordinator.async_set_channels(address, currents)
            except _ERRORS as exc:
                raise HomeAssistantError(f"SPOT {address} : {exc}") from exc


async def _handle_set_channel(call: ServiceCall) -> None:
    channel = int(call.data["channel"])
    ma = int(call.data["ma"])
    for coordinator in _coordinators(call.hass):
        gid = _group_target(call.data["address"])
        if gid is not None:
            _require_group(coordinator, gid)
            try:
                results = await coordinator.async_set_channel_group(gid, channel, ma)
            except _ERRORS as exc:
                raise HomeAssistantError(f"Groupe {gid} : {exc}") from exc
            _raise_if_group_errors(gid, results)
            continue
        for address in _addresses(call.data["address"], coordinator):
            spot = coordinator.data.spots[address]
            base = list(spot.currents) if spot.currents else [0] * 16
            if not 1 <= channel <= len(base):
                raise ServiceValidationError(
                    f"canal {channel} hors limites (1..{len(base)}) pour SPOT {address}"
                )
            base[channel - 1] = ma
            try:
                await coordinator.async_set_channels(address, base)
            except _ERRORS as exc:
                raise HomeAssistantError(f"SPOT {address} : {exc}") from exc


# ---------------------------------------------------------------------------
# Gestion des groupes de luminaires depuis l'UI (set_group / remove_group)
# ---------------------------------------------------------------------------


def _group_coordinator(
    hass: HomeAssistant, call: ServiceCall, group_id: str | None = None
) -> Phs16Coordinator:
    """Coordinator cible : celui du bus `port` si donné, sinon celui qui connaît
    déjà `group_id`, sinon le premier bus (création d'un nouveau groupe)."""
    coordinators = _coordinators(hass)
    if not coordinators:
        raise ServiceValidationError("intégration phs16lc non chargée (aucune entrée)")
    port = str(call.data.get("port") or "").strip()
    if port:
        for coordinator in coordinators:
            if str(entry_value(coordinator.entry, CONF_PORT)) == port:
                return coordinator
        ports = [str(entry_value(c.entry, CONF_PORT)) for c in coordinators]
        raise ServiceValidationError(f"bus {port!r} introuvable (bus connus : {ports})")
    if group_id:
        for coordinator in coordinators:
            if group_id in coordinator.groups:
                return coordinator
    return coordinators[0]


def _parse_group_addresses(raw: object, coordinator: Phs16Coordinator) -> list[int]:
    """Champ `addresses` de set_group : "1,2,3", [1, 2] ou "all" (SPOT connus).

    Une adresse inconnue du scan est acceptée : on peut définir un groupe avant
    que la carte soit en ligne (le scan s'arrête au premier silence).
    """
    text = str(raw).strip()
    if text.lower() == "all":
        return sorted(coordinator.data.spots)
    values = list(raw) if isinstance(raw, (list, tuple)) else text.replace(",", " ").split()
    try:
        addresses = sorted({int(v) for v in values})
    except TypeError, ValueError:
        raise ServiceValidationError(
            f"addresses invalides : {raw!r} (entiers séparés par des virgules, ou 'all')"
        ) from None
    if not addresses or addresses[0] < 1:
        raise ServiceValidationError(f"addresses invalides : {raw!r} (entiers >= 1 requis)")
    return addresses


def _spot_addresses_from_entities(
    hass: HomeAssistant, coordinator: Phs16Coordinator, entity_ids: object
) -> list[int]:
    """Résout les entités `light` sélectionnées (multi-sélecteur UI) en adresses SPOT
    via l'unique_id `<entry_id>_spot_<n>_light`. Appelé sur le event loop (registre)."""
    registry = er.async_get(hass)
    pattern = re.compile(rf"^{re.escape(coordinator.entry.entry_id)}_spot_(\d+)_light$")
    addresses: list[int] = []
    for entity_id in entity_ids or []:  # type: ignore[union-attr]
        reg_entry = registry.async_get(str(entity_id))
        match = pattern.match(reg_entry.unique_id) if reg_entry is not None else None
        if match is None:
            raise ServiceValidationError(
                f"{entity_id} n'est pas un luminaire SPOT — sélectionnez des entités light.spot_*"
            )
        addresses.append(int(match.group(1)))
    if not addresses:
        raise ServiceValidationError("sélectionnez au moins un luminaire (spots)")
    return sorted(set(addresses))


async def _handle_set_group(call: ServiceCall) -> None:
    """Crée ou modifie un groupe de luminaires (écrit groups.json, rechargé à chaud).

    Sémantique de mise à jour partielle : seuls les champs fournis sont modifiés ;
    `spots`/`addresses` remplacent la liste des membres (attacher/détacher) ;
    chaîne vide = efface la valeur (sauf name qui retombe sur l'id).
    """
    group_id = str(call.data["group_id"]).strip()
    if not GROUP_ID_RE.match(group_id):
        raise ServiceValidationError(
            f"group_id invalide : {group_id!r} (caractères autorisés : A-Z a-z 0-9 _ -)"
        )
    new_id = str(call.data.get("new_group_id") or "").strip() or None
    if new_id is not None and not GROUP_ID_RE.match(new_id):
        raise ServiceValidationError(f"new_group_id invalide : {new_id!r}")
    coordinator = _group_coordinator(call.hass, call, group_id)
    if new_id and new_id != group_id and new_id in coordinator.groups:
        raise ServiceValidationError(f"le groupe {new_id!r} existe déjà")
    path = groups_file_for(recipes_dir_for_entry(coordinator.entry))

    # résolution des entités -> adresses SUR le event loop (registre d'entités)
    if "spots" in call.data:
        spot_addresses = _spot_addresses_from_entities(call.hass, coordinator, call.data["spots"])
    elif "addresses" in call.data:
        spot_addresses = _parse_group_addresses(call.data["addresses"], coordinator)
    else:
        spot_addresses = None

    def _do() -> None:
        groups = load_groups(path)
        gid = group_id
        if new_id and new_id != group_id:
            if group_id in groups:
                groups[new_id] = groups.pop(group_id)
            gid = new_id
        group = groups.get(gid) or GroupDef(id=gid, name=gid, addresses=[])
        if "name" in call.data:
            name = str(call.data["name"]).strip()
            group.name = name or gid
        if spot_addresses is not None:
            group.addresses = spot_addresses
        if "color" in call.data:
            color = str(call.data["color"]).strip()
            group.color = color or None
        if "icon" in call.data:
            icon = str(call.data["icon"]).strip()
            group.icon = icon or None
        if "area" in call.data:
            area = str(call.data["area"]).strip()
            group.area = area or None
        if not group.addresses:
            raise ServiceValidationError(
                f"le groupe {gid!r} doit contenir au moins un luminaire — "
                "renseignez `spots` ou `addresses`"
            )
        groups[gid] = group
        save_groups(path, groups)

    await coordinator.async_io(_do)
    await coordinator.async_reload_groups_now()


async def _handle_remove_group(call: ServiceCall) -> None:
    """Supprime un groupe de luminaires (groups.json réécrit, rechargé à chaud)."""
    group_id = str(call.data["group_id"]).strip()
    coordinator = _group_coordinator(call.hass, call, group_id)
    path = groups_file_for(recipes_dir_for_entry(coordinator.entry))

    def _do() -> None:
        groups = load_groups(path)
        if group_id not in groups:
            raise ServiceValidationError(
                f"groupe {group_id!r} inconnu — groupes connus : {sorted(groups) or 'aucun'}"
            )
        del groups[group_id]
        save_groups(path, groups)

    await coordinator.async_io(_do)
    await coordinator.async_reload_groups_now()


async def _handle_save_recipe(call: ServiceCall) -> None:
    """Enregistre les courants d'un SPOT comme une nouvelle recette (JSON v1 `channels`).

    `currents` optionnel : vecteur explicite (ex. positions des sliders de la carte
    Lovelace, qui peuvent ne pas encore être reflétées par le polling) ; sinon les
    courants lus au dernier polling du SPOT sont utilisés. Refuse d'écraser une
    recette existante sauf `overwrite: true`.
    """
    raw_name = str(call.data["name"]).strip()
    if raw_name.endswith(".json"):
        raw_name = raw_name[: -len(".json")]
    name = _safe_filename(raw_name)
    if not name:
        raise ServiceValidationError("name vide")
    description = str(call.data.get("description") or "").strip()
    overwrite = bool(call.data.get("overwrite", False))
    currents_raw = call.data.get("currents")
    for coordinator in _coordinators(call.hass):
        if (
            _group_target(call.data["address"]) is not None
            or str(call.data["address"]).strip().lower() == "all"
        ):
            raise ServiceValidationError("save_recipe cible l'adresse d'un seul SPOT")
        for address in _addresses(call.data["address"], coordinator):
            spot = coordinator.data.spots[address]
            if currents_raw is not None:
                currents = _parse_currents(currents_raw)
                if spot.currents and len(currents) != len(spot.currents):
                    raise ServiceValidationError(
                        f"SPOT {address} a {len(spot.currents)} canaux, "
                        f"{len(currents)} valeurs fournies"
                    )
            else:
                if not spot.online or not spot.currents:
                    raise ServiceValidationError(
                        f"SPOT {address} hors ligne ou courants inconnus "
                        "— attente du prochain polling"
                    )
                currents = list(spot.currents)
            path = recipes_dir_for_entry(coordinator.entry) / f"{name}.json"

            def _do(path=path, name=name, description=description, currents=currents) -> None:
                if path.exists() and not overwrite:
                    raise ServiceValidationError(
                        f"la recette {name!r} existe déjà (overwrite=true pour écraser)"
                    )
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "name": name,
                    "description": description,
                    "channels": [int(v) for v in currents],
                }
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                tmp.replace(path)

            await coordinator.async_io(_do)


_HANDLERS = {
    "scan": _handle_scan,
    "apply_recipe": _handle_apply_recipe,
    "apply_scene": _handle_apply_scene,
    "save": _handle_save,
    "save_recipe": _handle_save_recipe,
    "set_channels": _handle_set_channels,
    "set_channel": _handle_set_channel,
    "set_group": _handle_set_group,
    "remove_group": _handle_remove_group,
}


def async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services du domaine (idempotent)."""
    for name, handler in _HANDLERS.items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler)


def async_unregister_services(hass: HomeAssistant) -> None:
    """Retire les services du domaine (quand la dernière entrée est déchargée)."""
    for name in SERVICES:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
