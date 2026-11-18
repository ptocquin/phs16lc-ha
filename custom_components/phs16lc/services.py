"""Handlers des services `phs16lc.*` (décrits dans services.yaml + traductions).

`address` accepte un numéro de carte ("1") ou "all" (toutes les cartes connues
du coordinator). Enregistrement idempotent (plusieurs entrées = plusieurs bus) ;
les services sont retirés quand la dernière entrée est déchargée.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .coordinator import Phs16Coordinator
from .phs16ctl.controller import LuminaireError

SERVICES = ("scan", "apply_recipe", "apply_scene", "save", "set_channels", "set_channel")

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


_HANDLERS = {
    "scan": _handle_scan,
    "apply_recipe": _handle_apply_recipe,
    "apply_scene": _handle_apply_scene,
    "save": _handle_save,
    "set_channels": _handle_set_channels,
    "set_channel": _handle_set_channel,
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
