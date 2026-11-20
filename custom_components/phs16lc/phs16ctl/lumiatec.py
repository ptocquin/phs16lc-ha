"""Codec de la gamme lumiatec PHS-16 (Twindev / GDTech), bus RS-485 half-duplex 2 fils.

Validé sur luminaires réels (fw V1.3, adresses 131 et 136, adaptateur
USB-RS485 2 fils) le 2026-11-19 — trames mesurées dans PLAN_LUMIATEC.md §0.4
et §0.5 (réseau master/slave).

Différences vs PHS16-LC RevD (`protocol.REVD`) :

- adresse en **décimal** dans la trame (« 0x.. » aussi accepté par le
  firmware) ; checksum de la requête en **décimal** (le fw V1.3 ne le vérifie
  pas, on envoie le bon) ; réponses « #TAG args*XX » en hex (somme depuis le
  '#'), terminées par **CRLF** ; « ACK » / « NAK n » **sans** checksum ;
- commandes : GI GL GB GE GT GF GS (lecture), GC SC SF SS SV (écriture),
  RST, UP/FF (flash XMODEM) — **pas** de GU/UNP/DI/PRG ni GP ;
- 16 canaux numérotés **0..15** ; courant d'un canal = step × 5,7 mA,
  step 0 = éteint, plafond **step 87** (≈ 496 mA, fw V1.3 — overdrive réservé
  au fw ≥ V1.4, NAK 4 sinon) ; fenêtre PWM par canal 0..200 ;
- `@SF` : bit0 = power, bit1 = **master** — un seul master par bus, et il est
  obligatoire pour que la sortie PWM démarre (sinon ACK mais pas de lumière) ;
- quirk : le firmware écrit « O » au lieu de « 0 » dans les champs hex
  (« OxFFFF ») — voir `fix_hex_O()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import protocol as proto
from .protocol import Dialect, Response, build_frame

if TYPE_CHECKING:
    from .controller import Recipe
    from .link import PhsLink

#: Dialect lumiatec : adresse décimale, checksum requête décimal, filtre d'écho.
LUMIATEC = Dialect(name="lumiatec", addr_hex=False, chk_hex=False, echo_filter=True)

BAUDRATE = 115200

# Timeouts (s) — mesurés sur bus réel : réponses < 50 ms, @SV lent (> 0,6 s).
T_SCAN = 0.2     # @GI pendant le scan (silence = adresse absente), comme PHS16-LC
T_DEFAULT = 1.0  # lecture/écriture standard (code d'origine : 1 s uniforme)
T_SV = 2.0       # @SV : écriture EEPROM, ACK observé après plus de 0,6 s

#: Nombre de canaux d'un luminaire lumiatec (@GC 16 -> NAK 4, mesuré).
N_CHANNELS = 16

#: Courant par step de canal : 1140 mA / 200 steps = 5,7 mA (code d'origine).
STEP_MA = 1140 / 200

#: Step max accepté par @SC sur fw V1.3 (overdrive 0) : 88 -> NAK 6 (mesuré).
STEP_MAX = 87

#: i_peek d'un canal lu dans le descripteur @GB : step × 5 mA (code d'origine).
IPEKK_MA_PER_STEP = 5

# Bits du bitmask @SF (fw V1.3 : seuls les bits 0 et 1 sont valides).
SF_POWER = 1
SF_MASTER = 2


def sf_bitmask(power: bool, master: bool) -> int:
    """Bitmask @SF : bit0 = power, bit1 = master."""
    return (SF_POWER if power else 0) | (SF_MASTER if master else 0)


def ma_to_step(ma: float) -> int:
    """mA -> step de canal (0 = éteint, plafond STEP_MAX)."""
    if ma <= 0:
        return 0
    return min(STEP_MAX, round(ma / STEP_MA))


def step_to_ma(step: int) -> float:
    """Step de canal -> mA."""
    return step * STEP_MA


def build_frame_lum(cmd: str, addr: int, params: str = "") -> bytes:
    """Trame lumiatec : `@CMD <addr> <params>*<chk décimal>\\r` (ex. b'@GI 136 *170\\r')."""
    return build_frame(cmd, addr, params, dialect=LUMIATEC)


def response_checksum_ok(resp: Response) -> bool:
    """Vérifie le checksum hex des réponses « #TAG ...*XX » (ACK/NAK n'en ont pas)."""
    raw = resp.raw
    if not raw.startswith("#") or "*" not in raw:
        return True
    body, cs = raw.split("*", 1)
    cs2 = cs.strip()[:2]
    try:
        return len(cs2) == 2 and int(cs2, 16) == (sum(body.encode("ascii")) & 0xFF)
    except ValueError:
        return False


def fix_hex_O(s: str) -> str:
    """Remplace les « O » par des « 0 » dans un champ hex du firmware (« OxFFFF » -> « 0xFFFF »)."""
    return s.replace("O", "0")


def decode_ge(resp: Response) -> tuple[str, int] | None:
    """Décode « #GE <config> <drivers-hex> » -> (config, bitmask drivers)."""
    args = resp.args("#GE")
    if args is None or len(args) < 2:
        return None
    try:
        return args[0], int(fix_hex_O(args[1]), 16)
    except ValueError:
        return None


def decode_gf(resp: Response) -> int | None:
    """Décode « #GF <bitmask-hex> » -> bitmask config (bit0 power, bit1 master)."""
    args = resp.args("#GF")
    if args is None or not args:
        return None
    try:
        return int(fix_hex_O(args[0]), 16)
    except ValueError:
        return None


def decode_gc(resp: Response) -> tuple[int, int, int, int] | None:
    """Décode « #GC <ch> <step> <pwm_start> <pwm_stop> »."""
    args = resp.args("#GC")
    if args is None or len(args) < 4:
        return None
    try:
        return int(args[0]), int(args[1]), int(args[2]), int(args[3])
    except ValueError:
        return None


def _decrypt_led(data: str, length_bits: int, coding: str) -> tuple[object, str, str]:
    """Portage de lumiatec_phs16.decrypt_led : découpe le dump @GB (little-endian si > 8 bits).

    Retourne (valeur, chunk hex brut, reste de la chaîne).
    """
    n = 2 * length_bits // 8
    chunk, rest = data[:n], data[n:]
    if len(chunk) < n:
        return None, chunk, rest
    octets = [chunk[i : i + 2] for i in range(0, n, 2)]
    if length_bits > 8:
        octets.reverse()
    joined = "".join(octets)
    if coding == "int":
        try:
            value = int(joined, 16)
        except ValueError:
            value = None
    elif coding == "hex":
        value = "0x" + joined
    else:  # text
        try:
            value = bytearray.fromhex(joined).decode("latin-1")
        except ValueError:
            value = None
    return value, chunk, rest


def decode_led_descriptor(hexblob: str) -> dict:
    """Décode le dump « @GB » : CRC16, type16, SN32, puis la liste des canaux.

    Chaque canal : i_peek (8 bits, × 5 = mA), manuf (8 bits texte),
    col (16 bits texte, ex. « RE » ; `col_raw` garde le hex brut), wl (16 bits
    little-endian, nm). Retourne {"crc", "type", "sn", "channels": [...]}.
    """
    out: dict = {"channels": []}
    crc, _, rest = _decrypt_led(hexblob, 16, "hex")
    pcb_type, _, rest = _decrypt_led(rest, 16, "int")
    sn, _, rest = _decrypt_led(rest, 32, "hex")
    out["crc"], out["type"], out["sn"] = crc, pcb_type, sn
    while rest:
        i_peek_step, _, rest = _decrypt_led(rest, 8, "int")
        manuf, _, rest = _decrypt_led(rest, 8, "text")
        col, col_raw, rest = _decrypt_led(rest, 16, "text")
        wl, _, rest = _decrypt_led(rest, 16, "int")
        if None in (i_peek_step, manuf, col, wl):
            break
        label = "".join(c for c in col[::-1] if c.isprintable())  # comme le code d'origine
        out["channels"].append(
            {
                "i_peek": i_peek_step * IPEKK_MA_PER_STEP,  # mA
                "manuf": manuf,
                "col": label,
                "col_raw": col_raw,
                "wl_nm": wl,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Couche contrôle (phase 2) — même API que controller.Luminaire
# ---------------------------------------------------------------------------

FAMILY_PHS16LC = "phs16-lc"
FAMILY_LUMIATEC = "lumiatec"
FAMILIES = (FAMILY_PHS16LC, FAMILY_LUMIATEC)

#: Courant par défaut pour `on()` (mA) — comme controller.DEFAULT_CURRENT_MA.
DEFAULT_CURRENT_MA = 500


def _controller_error(msg: str) -> Exception:
    """LuminaireError du controller (import tardif : évite le cycle controller <-> lumiatec)."""
    from .controller import LuminaireError

    return LuminaireError(msg)


def scan_line(link: "PhsLink", expected: int = 0, max_addr: int = 255,
              timeout: float = T_SCAN) -> list[int]:
    """Énumère les adresses présentes sur la ligne lumiatec.

    Les adresses lumiatec ne sont **pas contiguës** (ex. 131, 136) : pas
    d'arrêt au premier silence. `expected > 0` balaie 1..expected ; sinon
    1..max_addr (défaut 255).
    """
    found: list[int] = []
    top = expected if expected > 0 else max_addr
    for address in range(1, top + 1):
        if link.send("GI", address, timeout=timeout) is not None:
            found.append(address)
    return found


def set_sf(link: "PhsLink", address: int, bitmask: int) -> None:
    """@SF <bitmask> sur un luminaire (ACK exigé)."""
    resp = link.send("SF", address, str(bitmask), timeout=T_DEFAULT)
    if resp is None:
        raise _controller_error(f"Pas de réponse @SF à l'adresse {address}")
    if resp.is_nak:
        raise _controller_error(f"@SF refusé (adresse {address}) : {resp.error}")


def ge_ok(link: "PhsLink", address: int) -> bool | None:
    """@GE sur un luminaire : True si `OK`, False si `ERR`, None si pas de réponse."""
    resp = link.send("GE", address, timeout=T_DEFAULT)
    if resp is None:
        return None
    decoded = decode_ge(resp)
    return bool(decoded and decoded[0] == "OK")


def elect_master(addresses: list[int], link: "PhsLink | None" = None,
                 prefer: int | None = None) -> int:
    """Adresse du master du bus — assigné UNIQUEMENT à la (ré)initialisation du
    réseau (scan/découverte), jamais en cours de route.

    **Règle mesurée en production (2026-11-20, bus 131/136)** : le fw exige que le
    master soit le luminaire **physiquement premier sur le bus (côté PC)** — pas
    forcément la plus petite adresse : avec 131 master, `@GE` = ERR chez l'autre
    spot (0/10 lectures OK) et le slave reste noir malgré `@SC` ACKé ; avec 136
    master, `@GE` = OK (8/10) et tout le bus s'allume. Un seul master à la fois :
    chaque candidate réécrit le `@SF` de **tous** les spots (jamais 2 masters).

    Élection : `prefer` (option explicite) si présent dans les adresses ; sinon
    essai de chaque candidate par ordre croissant, validée si un **autre** spot
    répond `@GE OK` (au moins 1 lecture OK sur 5 — un master invalide ne donne
    jamais OK chez les autres ; ne pas sonder la candidate elle-même, son propre
    `@GE` flapote quand le PWM tourne). Repli : `min(addresses)` (code d'origine)
    si aucune candidate validée ou pas de `link`.
    """
    if not addresses:
        raise _controller_error("elect_master : aucune adresse fournie")
    if link is None:  # hors ligne : pas d'élection possible
        return prefer if prefer in addresses else min(addresses)
    chosen = prefer if prefer in addresses else None
    if chosen is None:
        for candidate in sorted(addresses):
            for a in addresses:
                set_sf(link, a, sf_bitmask(True, a == candidate))
            # sonde @GE chez les autres spots (pas chez la candidate)
            for a in addresses:
                if a == candidate:
                    continue
                for _ in range(5):
                    if ge_ok(link, a) is True:
                        chosen = candidate
                        break
                if chosen is not None:
                    break
            if chosen is not None:
                break
    if chosen is None:
        chosen = min(addresses)  # repli : aucun candidat validé par @GE
    # applique l'assignation retenue : power partout, master sur un seul
    for a in addresses:
        set_sf(link, a, sf_bitmask(True, a == chosen))
    return chosen


def apply_power(addresses: list[int], link: "PhsLink", power: bool = True,
                master_addr: int | None = None) -> None:
    """Positionne le bit power sur tous les luminaires, et master sur l'élu.

    À appeler avant toute commande produisant de la lumière : sans power+master,
    le fw V1.3 acquitte (`@SC` -> ACK, `@GC` relit la valeur) mais ne sort pas
    de PWM. Un seul master par bus. `master_addr` : élu par défaut via
    `elect_master(addresses, link)` (validation `@GE OK` chez les autres spots).
    """
    if master_addr is None:
        master_addr = elect_master(addresses, link)
    for a in addresses:
        set_sf(link, a, sf_bitmask(power, a == master_addr))


class LuminaireLumiatec:
    """Un luminaire lumiatec adressé sur la ligne (fw V1.3 observé).

    Même API que `controller.Luminaire` : `on` / `off` / `set_channels` /
    `apply_recipe` / `save` / `read_currents` / `read_temperatures`.
    Les canaux sont 0-based côté bus ; les courants sont exposés en **mA**
    (step × 5,7, plafond 87) comme pour PHS16-LC, les recettes (1-based)
    s'appliquent telles quelles.

    Le lien (`link`) doit porter le dialect `LUMIATEC` (voir `make_link`).
    `master=True` positionne le bit master de `@SF` — obligatoire pour la
    sortie PWM, un seul master par bus (voir `elect_master`).
    """

    def __init__(self, address: int, link: "PhsLink", channels: int = N_CHANNELS,
                 master: bool = False, currents: list[int] | None = None) -> None:
        self.address = address
        self.link = link
        self.channels = channels
        self.master = master
        self.currents: list[int] = list(currents) if currents is not None else []

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------
    def _require_ack(self, resp: Response | None, what: str) -> Response:
        if resp is None:
            raise _controller_error(f"Pas de réponse {what} à l'adresse {self.address}")
        if resp.is_nak:
            raise _controller_error(f"{what} refusé (adresse {self.address}) : {resp.error}")
        return resp

    # ------------------------------------------------------------------
    # Power / master (@SF)
    # ------------------------------------------------------------------
    def set_power(self, power: bool, master: bool | None = None) -> None:
        """@SF : bit0 = power, bit1 = master (défaut = self.master)."""
        m = self.master if master is None else master
        resp = self.link.send("SF", self.address, str(sf_bitmask(power, m)), timeout=T_DEFAULT)
        self._require_ack(resp, "@SF")

    # ------------------------------------------------------------------
    # Allumer / éteindre
    # ------------------------------------------------------------------
    def on(self, current_ma: int = DEFAULT_CURRENT_MA) -> None:
        """Allume : power+master (@SF) puis tous les canaux à `current_ma`."""
        self.set_power(power=True)
        self.set_channels([current_ma] * self.channels)

    def off(self) -> None:
        """Éteint tous les canaux (step 0). Laisse power/master tels quels."""
        self.set_channels([0] * self.channels)

    def shutdown(self) -> None:
        """Extinction complète : canaux à 0 + power OFF + master OFF (@SF 0)."""
        self.set_channels([0] * self.channels)
        self.set_power(power=False, master=False)

    # ------------------------------------------------------------------
    # Canaux
    # ------------------------------------------------------------------
    def set_channels(self, currents: list[int]) -> None:
        """Programme les courants (mA) de chaque canal : N × @SC (volatil)."""
        if len(currents) != self.channels:
            raise _controller_error(
                f"Luminaire {self.address} : {self.channels} canaux attendus, "
                f"{len(currents)} reçus"
            )
        steps = [ma_to_step(ma) for ma in currents]
        for ch, step in enumerate(steps):
            resp = self.link.send("SC", self.address, f"{ch} {step} 0 200", timeout=T_DEFAULT)
            self._require_ack(resp, "@SC")
        self.currents = [round(step_to_ma(s)) for s in steps]

    def apply_recipe(self, recipe: "Recipe", group: str | None = None) -> None:
        """Applique une recette (mêmes fichiers JSON que PHS16-LC).

        Sans `group` : recette complète. Avec `group` : lecture des courants
        actuels (@GC), patch du groupe (canaux 1-based de la recette), renvoi.
        """
        if group is None:
            self.set_channels(recipe.full_vector(self.channels))
            return
        g = recipe.group(group)
        base = self.read_currents()
        for c in g.channels:
            if not 1 <= c <= self.channels:
                raise _controller_error(
                    f"Recette '{recipe.name}' : groupe '{group}', canal {c} "
                    f"hors limites (1..{self.channels})"
                )
            base[c - 1] = g.current
        self.set_channels(base)

    # ------------------------------------------------------------------
    # Persistance NVM
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Sauvegarde la configuration en NVM (@SV, lent : timeout 2 s)."""
        resp = self.link.send("SV", self.address, timeout=T_SV)
        self._require_ack(resp, "@SV")

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def read_currents(self) -> list[int]:
        """Lit les courants (mA) de chaque canal : N × @GC."""
        out: list[int] = []
        for ch in range(self.channels):
            resp = self.link.send("GC", self.address, str(ch), timeout=T_DEFAULT)
            if resp is None:
                raise _controller_error(f"Pas de réponse @GC canal {ch} (adresse {self.address})")
            gc = decode_gc(resp)
            if gc is None or gc[0] != ch:
                raise _controller_error(f"Réponse @GC illisible canal {ch} (adresse {self.address})")
            out.append(round(step_to_ma(gc[1])))
        self.currents = out
        return out

    def read_temperatures(self) -> tuple[float, float, float]:
        """Températures (@GT) : (CPU, carte LED 1, carte LED 2) en °C."""
        resp = self.link.send("GT", self.address, timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GT à l'adresse {self.address}")
        temps = proto.decode_temperatures(resp)
        if temps is None:
            raise _controller_error(f"Réponse @GT illisible à l'adresse {self.address}")
        return temps

    def read_identity(self) -> tuple[int, str]:
        """Identité (@GI) : (numéro de série, version firmware)."""
        resp = self.link.send("GI", self.address, timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GI à l'adresse {self.address}")
        ident = proto.decode_identity(resp)
        if ident is None:
            raise _controller_error(f"Réponse @GI illisible à l'adresse {self.address}")
        return ident

    def read_status(self) -> tuple[str, int]:
        """Statut (@GE) : (config « OK »/« ERR », bitmask drivers)."""
        resp = self.link.send("GE", self.address, timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GE à l'adresse {self.address}")
        status = decode_ge(resp)
        if status is None:
            raise _controller_error(f"Réponse @GE illisible à l'adresse {self.address}")
        return status

    def read_config(self) -> dict:
        """Config (@GF + @GS) : bitmask, power, master, fréquence PWM (Hz)."""
        resp = self.link.send("GF", self.address, timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GF à l'adresse {self.address}")
        bitmask = decode_gf(resp)
        if bitmask is None:
            raise _controller_error(f"Réponse @GF illisible à l'adresse {self.address}")
        resp = self.link.send("GS", self.address, timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GS à l'adresse {self.address}")
        args = resp.args("#GS")
        freq_hz = float(args[0]) / 10 if args else None
        return {
            "bitmask": bitmask,
            "power": bool(bitmask & SF_POWER),
            "master": bool(bitmask & SF_MASTER),
            "freq_hz": freq_hz,
        }

    def read_led_descriptor(self, board: int = 0) -> dict:
        """Descripteur de carte LED (@GB) : canaux, i_peek, couleurs, λ."""
        resp = self.link.send("GB", self.address, str(board), timeout=T_DEFAULT)
        if resp is None:
            raise _controller_error(f"Pas de réponse @GB à l'adresse {self.address}")
        args = resp.args("#GB")
        if args is None or len(args) < 2:
            raise _controller_error(f"Réponse @GB illisible à l'adresse {self.address}")
        return decode_led_descriptor(args[1])


# ---------------------------------------------------------------------------
# Factories (phase 2) — le reste du programme choisit la famille ici
# ---------------------------------------------------------------------------

def make_link(family: str, tx_port: str, rx_port: str | None = None,
              baudrate: int = BAUDRATE, trace=None) -> "PhsLink":
    """Construit un PhsLink avec le dialect de la famille (`phs16-lc` = défaut REVD)."""
    from .link import PhsLink

    dialect = LUMIATEC if family == FAMILY_LUMIATEC else None
    return PhsLink(tx_port, rx_port=rx_port, baudrate=baudrate, trace=trace, dialect=dialect)


def make_luminaire(family: str, address: int, link: "PhsLink", **kwargs):
    """Fabrique le contrôleur adapté à la famille : `phs16-lc` -> Luminaire, `lumiatec` -> LuminaireLumiatec."""
    if family == FAMILY_LUMIATEC:
        return LuminaireLumiatec(address=address, link=link, **kwargs)
    from .controller import Luminaire

    return Luminaire(address=address, link=link, **kwargs)
