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

from .protocol import Dialect, Response, build_frame

#: Dialect lumiatec : adresse décimale, checksum requête décimal, filtre d'écho.
LUMIATEC = Dialect(name="lumiatec", addr_hex=False, chk_hex=False, echo_filter=True)

BAUDRATE = 115200

# Timeouts (s) — mesurés sur bus réel : réponses < 50 ms, @SV lent (> 0,6 s).
T_SCAN = 0.5     # @GI pendant le scan (silence = adresse absente / fin de ligne)
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
