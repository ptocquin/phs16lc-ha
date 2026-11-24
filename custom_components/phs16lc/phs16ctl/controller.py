"""Contrôle orienté « recettes lumineuses » d'un luminaire PHS16-LC.

Au-dessus de la couche basse (protocol + link), ce module expose une classe
`Luminaire` avec des opérations simples : allumer, éteindre, régler canal
par canal, appliquer une recette, sauvegarder en NVM, scanner la ligne.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import lumiatec as lum
from . import protocol as proto
from .link import T_DI, T_GI, T_GP, T_GT, T_PRG, T_SP, T_UNP, T_WP, PhsLink

#: Courant par défaut pour `on()` quand aucun mA n'est précisé.
DEFAULT_CURRENT_MA = 500

#: Seuil d'alerte de température par défaut, en degrés Celsius.
DEFAULT_TEMP_THRESHOLD_C = 70.0


class LuminaireError(RuntimeError):
    """Échec d'une commande (pas un simple silence de la ligne)."""


def _check_current(recipe_name: str, where: str, ma: int) -> None:
    """Rejette un courant hors bornes avant tout envoi (0 = éteint, sinon 74–2150 mA)."""
    if ma < 0 or ma > proto.CURRENT_MAX_MA:
        raise LuminaireError(
            f"Recette '{recipe_name}' : {where} = {ma} mA hors bornes "
            f"(0 pour éteindre, ou {proto.CURRENT_MIN_MA}–{proto.CURRENT_MAX_MA} mA)"
        )


@dataclass
class ChannelGroup:
    """Groupe nommé de canaux réglés à un même courant (mA)."""

    name: str
    channels: list[int]  # numéros de canaux, base 1
    current: int         # mA


@dataclass
class Recipe:
    """Recette lumineuse, deux formes compatibles :

    - v1 : `channels` seul, vecteur complet de courants (mA) par canal ;
    - v2 : `groups`, groupes nommés ``{"channels": [...], "current": mA}`` ;
      lors d'une application complète, les canaux non couverts sont éteints.
    """

    name: str
    description: str = ""
    channels: list[int] | None = None
    groups: dict[str, ChannelGroup] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> "Recipe":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        groups = {
            gname: ChannelGroup(
                name=gname,
                channels=[int(c) for c in g["channels"]],
                current=int(g["current"]),
            )
            for gname, g in (data.get("groups") or {}).items()
        }
        channels = data.get("channels")
        return cls(
            name=data.get("name", Path(path).stem),
            description=data.get("description", ""),
            channels=[int(v) for v in channels] if channels is not None else None,
            groups=groups,
        )

    def group(self, name: str) -> ChannelGroup:
        """Retourne le groupe nommé, ou lève si la recette n'en définit pas."""
        try:
            return self.groups[name]
        except KeyError:
            available = ", ".join(self.groups) or "aucun"
            raise LuminaireError(
                f"Recette '{self.name}' : groupe '{name}' inconnu (disponibles : {available})"
            ) from None

    def validate(self, n_channels: int) -> None:
        """Valide la recette pour une carte de `n_channels` canaux (avant envoi)."""
        if self.channels is not None:
            if len(self.channels) != n_channels:
                raise LuminaireError(
                    f"Recette '{self.name}' : {len(self.channels)} canaux, "
                    f"la carte en a {n_channels}"
                )
            for i, ma in enumerate(self.channels, 1):
                _check_current(self.name, f"canal {i}", ma)
        seen: set[int] = set()
        for g in self.groups.values():
            _check_current(self.name, f"groupe '{g.name}'", g.current)
            for c in g.channels:
                if not 1 <= c <= n_channels:
                    raise LuminaireError(
                        f"Recette '{self.name}' : groupe '{g.name}', "
                        f"canal {c} hors limites (1..{n_channels})"
                    )
                if c in seen:
                    raise LuminaireError(
                        f"Recette '{self.name}' : canal {c} présent dans plusieurs groupes"
                    )
                seen.add(c)

    def full_vector(self, n_channels: int) -> list[int]:
        """Vecteur complet de courants (mA), validé puis clampé, prêt à l'envoi."""
        self.validate(n_channels)
        if self.channels is not None:
            return [proto.clamp_current(ma) for ma in self.channels]
        vector = [0] * n_channels
        for g in self.groups.values():
            for c in g.channels:
                vector[c - 1] = proto.clamp_current(g.current)
        return vector


@dataclass
class Luminaire:
    """Une carte driver PHS16-LC adressée sur la ligne."""

    address: int
    link: PhsLink
    channels: int = 16
    currents: list[int] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Allumer / éteindre
    # ------------------------------------------------------------------
    def on(self, current_ma: int = DEFAULT_CURRENT_MA) -> None:
        """Allume tous les canaux à `current_ma` (défaut 500 mA)."""
        self.set_channels([current_ma] * self.channels)

    def off(self) -> None:
        """Éteint tous les canaux (0 mA, soit < 74 mA)."""
        self.set_channels([0] * self.channels)

    # ------------------------------------------------------------------
    # Réglage canal par canal
    # ------------------------------------------------------------------
    def set_channels(self, currents: list[int]) -> None:
        """Programme les courants (mA) de chaque canal. Volatil jusqu'à save()."""
        if len(currents) != self.channels:
            raise LuminaireError(
                f"Carte {self.address} : {self.channels} canaux attendus, {len(currents)} reçus"
            )
        clamped = [proto.clamp_current(ma) for ma in currents]
        params = " ".join(str(ma) for ma in clamped) + " "
        resp = self.link.send("SP", self.address, params, timeout=T_SP)
        if resp is None:
            raise LuminaireError(f"Pas de réponse @SP à l'adresse {self.address}")
        if resp.is_nak:
            raise LuminaireError(f"@SP refusé (adresse {self.address}) : {resp.error}")
        self.currents = clamped

    def apply_recipe(self, recipe: Recipe, group: str | None = None) -> None:
        """Applique une recette lumineuse.

        Sans `group` : applique la recette complète (un courant par canal).
        Avec `group` : application partielle — lecture des courants actuels
        (@GP), puis seuls les canaux du groupe sont modifiés (@SP).
        """
        if group is None:
            self.set_channels(recipe.full_vector(self.channels))
            return
        g = recipe.group(group)
        _check_current(recipe.name, f"groupe '{group}'", g.current)
        base = self.read_currents()
        for c in g.channels:
            if not 1 <= c <= self.channels:
                raise LuminaireError(
                    f"Recette '{recipe.name}' : groupe '{group}', "
                    f"canal {c} hors limites (1..{self.channels})"
                )
            base[c - 1] = proto.clamp_current(g.current)
        self.set_channels(base)

    # ------------------------------------------------------------------
    # Persistance NVM
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Sauvegarde les courants courants en mémoire non volatile (@WP)."""
        resp = self.link.send("WP", self.address, timeout=T_WP)
        if resp is None:
            raise LuminaireError(f"Pas de réponse @WP à l'adresse {self.address}")
        if resp.is_nak:
            raise LuminaireError(f"@WP refusé (adresse {self.address}) : {resp.error}")

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def read_currents(self) -> list[int]:
        """Lit les courants actuels de chaque canal (@GP)."""
        resp = self.link.send("GP", self.address, timeout=T_GP)
        if resp is None:
            raise LuminaireError(f"Pas de réponse @GP à l'adresse {self.address}")
        currents = proto.decode_currents(resp)
        if currents is None:
            raise LuminaireError(f"Réponse @GP illisible à l'adresse {self.address}")
        self.channels = len(currents)
        self.currents = currents
        return currents

    def read_temperatures(self) -> tuple[float, float, float]:
        """Lit les températures (@GT) : (CPU, carte LED 1, carte LED 2) en °C."""
        resp = self.link.send("GT", self.address, timeout=T_GT)
        if resp is None:
            raise LuminaireError(f"Pas de réponse @GT à l'adresse {self.address}")
        temps = proto.decode_temperatures(resp)
        if temps is None:
            raise LuminaireError(f"Réponse @GT illisible à l'adresse {self.address}")
        return temps


def scan_line(link: PhsLink, expected: int = 0) -> list[int]:
    """Énumère les adresses présentes sur la ligne (1, 2, 3, ...).

    Par défaut (`expected=0`) : s'arrête au premier silence, considéré comme
    la fin de la ligne. Avec `expected > 0` : balaye toutes les adresses
    1..`expected` même si les premières sont muettes (ex. une seule carte
    programmée à l'adresse 2, l'adresse 1 étant vide), et retourne celles
    qui répondent.

    Une adresse ne compte que si la réponse est **plausible**
    (`Response.is_plausible` : tag ACK/NAK/#xx + checksum valide) — le bruit de
    ligne (bus long non blindé, diaphonie) ne doit pas créer de faux SPOT.
    """
    found: list[int] = []
    address = 1
    while True:
        resp = link.send("GI", address, timeout=T_GI)
        if resp is None or not resp.is_plausible:
            if expected > 0:
                # Balayage 1..expected : un silence n'arrête pas le scan,
                # même à l'adresse 1 (carte programmée à une adresse > 1).
                if address > expected:
                    break
                address += 1
                continue
            # expected == 0 : le premier silence est la fin de la ligne.
            break
        found.append(address)
        address += 1
    return found


# ------------------------------------------------------------------
# Provisionnement de la ligne (installation / ajout / remplacement)
# ------------------------------------------------------------------

#: @UNP en broadcast : nombre max de tentatives avant d'abandonner.
UNPROGRAM_MAX_TRIES = 20
#: @DI : nombre d'essais au silence avant de conclure à la fin de l'énumération.
DISCOVER_TRIES = 3
#: @PRG refusée pour un même SN : nombre d'essais avant d'abandonner.
PRG_MAX_FAILURES = 3
#: Délai après un @UNP bien reçu (laisse le fw appliquer le reset).
DELAY_AFTER_UNPROGRAM = 0.5
#: Délai entre deux @PRG (écriture NVM de l'adresse).
DELAY_AFTER_PRG = 0.15


@dataclass
class ProvisionedSpot:
    """Un SPOT auquel une adresse réseau vient d'être allouée (@PRG)."""

    address: int
    serial: int  # numéro de série (0x...)
    firmware: str


def provision_line(link: PhsLink, max_spots: int = 255) -> list[ProvisionedSpot]:
    """Reprogramme la ligne entière (README §5.2) : `@UNP` en broadcast répété
    jusqu'au silence (tous les SPOT repassent « non programmé »), puis boucle
    `@DI` / `@PRG` allouant les adresses 1..N par proximité au PC.

    /!\\ Réservé à l'installation et à l'ajout **manuel** d'un luminaire :
    ne JAMAIS appeler depuis un refresh périodique — un SPOT qui perd son
    adresse ne doit pas déclencher de reprogrammation automatique de la ligne.

    Lève LuminaireError si `@UNP` reste refusée (câblage / alim bus) ou si un
    `@PRG` est refusé plusieurs fois. Retourne les SPOT programmés (liste vide
    si aucun SPOT non programmé n'a répondu à `@DI`).
    """
    for _ in range(UNPROGRAM_MAX_TRIES):
        resp = link.send("UNP", 0, timeout=T_UNP)
        if resp is None:
            # silence = tous les SPOT ont décodé la commande
            time.sleep(DELAY_AFTER_UNPROGRAM)
            break
        # sinon réponse (NAK = mal décodé) : on recommence
    else:
        raise LuminaireError(
            f"@UNP toujours refusée après {UNPROGRAM_MAX_TRIES} tentatives — "
            "vérifier le câblage RS-485 et l'alimentation 12–24 V du bus"
        )
    spots: list[ProvisionedSpot] = []
    prg_failures: dict[int, int] = {}
    next_address = 1
    tries = DISCOVER_TRIES
    while next_address <= max_spots:
        resp = link.send("DI", 0, timeout=T_DI)
        if resp is None:
            tries -= 1
            if tries > 0:
                continue
            break  # plus de SPOT non programmé
        identity = proto.decode_identity(resp)
        if identity is None:
            tries = DISCOVER_TRIES
            time.sleep(0.05)
            continue
        serial_number, firmware = identity
        prg = link.send("PRG", 0, f"0x{serial_number:x} {next_address}", timeout=T_PRG)
        if prg is None or prg.is_nak:
            prg_failures[serial_number] = prg_failures.get(serial_number, 0) + 1
            if prg_failures[serial_number] >= PRG_MAX_FAILURES:
                raise LuminaireError(
                    f"@PRG refusée {PRG_MAX_FAILURES} fois pour le SPOT 0x{serial_number:08x}"
                )
            tries = DISCOVER_TRIES
            continue
        spots.append(
            ProvisionedSpot(address=next_address, serial=serial_number, firmware=firmware)
        )
        next_address += 1
        tries = DISCOVER_TRIES
        time.sleep(DELAY_AFTER_PRG)
    return spots


# ------------------------------------------------------------------
# Scènes multi-cartes
# ------------------------------------------------------------------

@dataclass
class SceneTarget:
    """Une entrée de scène : une recette (et un groupe optionnel) pour une ou plusieurs cartes."""

    addresses: list[int]
    recipe_ref: str
    group: str | None = None


@dataclass
class Scene:
    """Fichier de scène : applique des recettes à plusieurs cartes en une commande."""

    name: str
    description: str = ""
    targets: list[SceneTarget] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "Scene":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        targets = []
        for t in data["targets"]:
            addr = t["address"]
            addresses = [int(a) for a in addr] if isinstance(addr, list) else [int(addr)]
            targets.append(SceneTarget(
                addresses=addresses,
                recipe_ref=t["recipe"],
                group=t.get("group"),
            ))
        return cls(
            name=data.get("name", Path(path).stem),
            description=data.get("description", ""),
            targets=targets,
        )


@dataclass
class CardResult:
    """Résultat de l'application d'une scène sur une carte."""

    address: int
    ok: bool
    message: str
    recipe: str = ""   # nom de la recette appliquée
    group: str = ""    # groupe appliqué, le cas échéant


def _resolve_recipe_path(scene_path: Path, ref: str) -> Path:
    """Résout la référence de recette d'une scène.

    Ordre : chemin tel quel, puis relatif au dossier de la scène, puis dans
    le dossier `recipes/` voisin du dossier `scenes/`.
    """
    for candidate in (
        Path(ref),
        scene_path.parent / ref,
        scene_path.parent.parent / "recipes" / Path(ref).name,
    ):
        if candidate.is_file():
            return candidate
    raise LuminaireError(f"Recette '{ref}' introuvable (référencée depuis {scene_path})")


def apply_scene(
    link: PhsLink,
    scene: Scene,
    scene_path: str | Path,
    save: bool = False,
    family: str = lum.FAMILY_PHS16LC,
) -> list[CardResult]:
    """Applique chaque cible de la scène, carte par carte.

    Une carte en erreur n'interrompt pas les autres : le résultat est
    rapporté individuellement. `save=True` envoie la sauvegarde NVM après
    chaque carte (`@WP` en phs16-lc, `@SV` en lumiatec). `family` choisit le
    contrôleur de cartes (défaut `phs16-lc`).
    """
    scene_path = Path(scene_path)
    results: list[CardResult] = []
    for target in scene.targets:
        try:
            recipe = Recipe.from_file(_resolve_recipe_path(scene_path, target.recipe_ref))
        except (LuminaireError, OSError, ValueError, KeyError) as exc:
            for a in target.addresses:
                results.append(CardResult(a, False, f"recette illisible : {exc}"))
            continue
        for a in target.addresses:
            dev = lum.make_luminaire(family, a, link)
            try:
                dev.apply_recipe(recipe, group=target.group)
                if save:
                    dev.save()
            except LuminaireError as exc:
                results.append(CardResult(a, False, str(exc), recipe=recipe.name, group=target.group or ""))
                continue
            what = f"groupe '{target.group}'" if target.group else f"recette '{recipe.name}'"
            results.append(CardResult(a, True, what + (" + NVM" if save else ""),
                                      recipe=recipe.name, group=target.group or ""))
    return results


# ------------------------------------------------------------------
# Scan lisible
# ------------------------------------------------------------------

@dataclass
class CardInfo:
    """Carte trouvée par le scan, avec ses courants lus (@GP)."""

    address: int
    currents: list[int] | None  # None si @GP est resté muet

    @property
    def channels(self) -> int:
        return len(self.currents) if self.currents else 0


def scan_table(link: PhsLink, expected: int = 0) -> list[CardInfo]:
    """Scanne la ligne et lit les courants (@GP) de chaque carte trouvée."""
    infos: list[CardInfo] = []
    for address in scan_line(link, expected=expected):
        lum = Luminaire(address=address, link=link)
        try:
            currents = lum.read_currents()
        except LuminaireError:
            currents = None
        infos.append(CardInfo(address=address, currents=currents))
    return infos


def format_currents(currents: list[int]) -> str:
    """Résumé compact d'un vecteur de courants : « 500 mA × 16 », « 800×8 + 0×8 »…"""
    if not currents:
        return "?"
    if len(set(currents)) == 1:
        v = currents[0]
        return f"éteint × {len(currents)}" if v < proto.CURRENT_MIN_MA else f"{v} mA × {len(currents)}"
    # compression par plages identiques consecutives
    parts: list[tuple[int, int]] = []
    for v in currents:
        if parts and parts[-1][0] == v:
            parts[-1] = (v, parts[-1][1] + 1)
        else:
            parts.append((v, 1))
    return " + ".join(f"{v}×{n}" if n > 1 else str(v) for v, n in parts)
