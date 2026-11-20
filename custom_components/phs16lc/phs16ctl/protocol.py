"""Encodage / decodage des trames du protocole PHS16-LC (RevD).

Format d'une commande PC -> SPOT :

    @<CMD> 0x<addr> <arg1> ... <argN>*<CHK><CR>

Le checksum est la somme binaire 8 bits de tous les caracteres depuis le '@'
jusqu'au dernier caractere precedant le '*', encodee en 2 digits hexa ASCII
majuscules.  La trame se termine par un <CR> (0x0D) sans <LF>.

L'adresse 0 est un broadcast.  Elle est emise en hexadecimal prefixe '0x' et
suivie d'un espace, y compris lorsque la commande n'a aucun argument -- c'est
la forme exacte produite par MainWindow::sendCommand() du projet Qt GreenHouse,
conservee ici pour rester bit-a-bit compatible avec le firmware valide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CR = b"\r"

#: Separateurs utilises pour decouper une reponse (cf. decodeSN/decodeTemp Qt).
_SPLIT_RE = re.compile(r"[ \r\n*]+")

#: Codes d'erreur renvoyes par « NAK xx » (chapitre 4 du protocole).
NAK_ERRORS: dict[int, str] = {
    1: "Commande mal formatee",
    2: "Commande inconnue",
    3: "Mauvais compte d'arguments",
    4: "Valeur d'argument non valide",
    5: "Erreur de checksum",
    6: "Commande non encore implementee",
    7: "Erreur de lecture de l'EEPROM carte LED",
}

#: Bornes de courant par canal, en mA (chapitre 5.6).
CURRENT_MIN_MA = 74
CURRENT_MAX_MA = 2150


@dataclass(frozen=True)
class Dialect:
    """Format de trame d'une famille de luminaires.

    `addr_hex` / `chk_hex` décrivent la trame PC -> SPOT ; `echo_filter` active
    le rejet d'une trame reçue commençant par '@' (écho propre sur bus
    half-duplex). `REVD` (PHS16-LC) est le défaut de tous les appels existants
    et reste byte-identique ; les autres familles (ex. `lumiatec.LUMIATEC`)
    s'activent explicitement, jamais par défaut.
    """

    name: str
    addr_hex: bool  # True: adresse « 0x.. » en hexadécimal (PHS16-LC)
    chk_hex: bool   # True: checksum de la requête en 2 chiffres hex (PHS16-LC)
    echo_filter: bool = False  # True: ignorer l'écho de notre propre trame (half-duplex)


#: Dialect PHS16-LC RevD — défaut historique, inchangé.
REVD = Dialect(name="phs16-lc", addr_hex=True, chk_hex=True)


def checksum(payload: bytes) -> int:
    """Somme binaire 8 bits des octets de `payload` (du '@' au caractere avant '*')."""
    return sum(payload) & 0xFF


def build_frame(cmd: str, addr: int, params: str = "", dialect: Dialect | None = None) -> bytes:
    """Construit la trame complete, checksum et <CR> inclus.

    `dialect=None` vaut `REVD` (PHS16-LC) : byte-identique au format historique.
    """
    d = dialect if dialect is not None else REVD
    addr_s = f"0x{addr:x}" if d.addr_hex else str(addr)
    payload = b"@" + cmd.encode("ascii") + f" {addr_s} ".encode("ascii") + params.encode("ascii")
    chk = f"{checksum(payload):02X}" if d.chk_hex else str(checksum(payload))
    return payload + b"*" + chk.encode("ascii") + CR


@dataclass(frozen=True)
class Response:
    """Reponse d'un SPOT, decoupee en champs."""

    raw: str
    fields: tuple[str, ...]

    @classmethod
    def parse(cls, data: bytes) -> "Response":
        # Le firmware peut inserer des octets nuls sur la ligne : ils sont
        # filtres a la reception, comme dans MainWindow::readData().
        text = data.replace(b"\x00", b"").decode("ascii", errors="replace")
        fields = tuple(f for f in _SPLIT_RE.split(text) if f)
        return cls(raw=text.strip(), fields=fields)

    @property
    def tag(self) -> str:
        """Premier champ : « ACK », « NAK » ou « #XX » pour une reponse a donnees."""
        return self.fields[0] if self.fields else ""

    @property
    def is_ack(self) -> bool:
        return self.tag == "ACK"

    @property
    def is_nak(self) -> bool:
        return self.tag == "NAK"

    @property
    def nak_code(self) -> int | None:
        if not self.is_nak or len(self.fields) < 2:
            return None
        try:
            return int(self.fields[1])
        except ValueError:
            return None

    @property
    def error(self) -> str | None:
        """Libelle de l'erreur si la reponse est un NAK, sinon None."""
        if not self.is_nak:
            return None
        code = self.nak_code
        if code is None:
            return f"NAK non decodable ({self.raw!r})"
        return f"NAK {code} : {NAK_ERRORS.get(code, 'code inconnu')}"

    def args(self, tag: str) -> list[str] | None:
        """Arguments de la reponse si son tag correspond, sinon None.

        Le dernier champ est le checksum ASCII qui suit le '*' : il est retire.
        """
        if self.tag != tag:
            return None
        body = list(self.fields[1:])
        if body and _looks_like_checksum(body[-1]):
            body.pop()
        return body


def _looks_like_checksum(field: str) -> bool:
    return len(field) == 2 and all(c in "0123456789abcdefABCDEF" for c in field)


def parse_int(value: str) -> int:
    """Entier decimal, ou hexadecimal si prefixe 'x' / '0x' (chapitre 3)."""
    v = value.lower()
    if v.startswith("0x"):
        return int(v[2:], 16)
    if v.startswith("x"):
        return int(v[1:], 16)
    return int(v, 10)


def decode_identity(resp: Response) -> tuple[int, str] | None:
    """Decode une reponse « #DI » / « #GI » en (numero de serie, version firmware)."""
    for tag in ("#DI", "#GI"):
        args = resp.args(tag)
        if args is None or len(args) < 2:
            continue
        try:
            return parse_int(args[1]), args[0]
        except ValueError:
            return None
    return None


def decode_temperatures(resp: Response) -> tuple[float, float, float] | None:
    """Decode « #GT cpu board1 board2 » en degres Celsius."""
    args = resp.args("#GT")
    if args is None or len(args) < 3:
        return None
    try:
        return float(args[0]), float(args[1]), float(args[2])
    except ValueError:
        return None


def decode_currents(resp: Response) -> list[int] | None:
    """Decode « #GP v1 ... vN » en courants (mA) par canal.

    Le nombre de canaux n'est pas annonce : il est deduit du nombre de champs,
    comme dans MainWindow::decodePWM() -- une carte repond soit 8, soit 16 valeurs.
    """
    args = resp.args("#GP")
    if args is None:
        return None
    channels = 16 if len(resp.fields) > 12 else 8
    try:
        return [int(v, 10) for v in args[:channels]]
    except ValueError:
        return None


def decode_led_boards(resp: Response) -> list[tuple[int, int]] | None:
    """Decode « #GL type1 sn1 type2 sn2 » en [(type, numero de serie), ...].

    Un type 0 signifie carte absente ou EEPROM non programmee.
    """
    args = resp.args("#GL")
    if args is None or len(args) < 4:
        return None
    try:
        return [(parse_int(args[0]), parse_int(args[1])), (parse_int(args[2]), parse_int(args[3]))]
    except ValueError:
        return None


#: Bornes des parametres ventilateur (chapitres 5.13 et 5.14).
FAN_LOW_TEMP_RANGE = (0, 74)
FAN_HIGH_TEMP_RANGE = (1, 75)
FAN_DUTY_RANGE = (0, 100)


@dataclass(frozen=True)
class FanSettings:
    """Programmation du ventilateur d'un SPOT."""

    #: Temperature de demarrage du ventilateur, en degres Celsius.
    low_temp: int
    #: Temperature a laquelle le ventilateur est a pleine vitesse.
    high_temp: int
    #: Seuil de demarrage, en pourcent de la vitesse maximale.
    min_duty: int

    def as_params(self) -> str:
        return f"{self.low_temp} {self.high_temp} {self.min_duty}"


def decode_fan_settings(resp: Response) -> FanSettings | None:
    """Decode « #GF low high duty »."""
    args = resp.args("#GF")
    if args is None or len(args) < 3:
        return None
    try:
        return FanSettings(int(args[0]), int(args[1]), int(args[2]))
    except ValueError:
        return None


def validate_fan_settings(settings: FanSettings) -> str | None:
    """Retourne un message d'erreur si les valeurs sont hors bornes, sinon None.

    Les bornes sont verifiees ici plutot que de laisser le SPOT repondre
    « NAK 4 », qui n'indiquerait pas quel parametre est en cause.
    """
    for value, (low, high), label in (
        (settings.low_temp, FAN_LOW_TEMP_RANGE, "temperature de demarrage"),
        (settings.high_temp, FAN_HIGH_TEMP_RANGE, "temperature de pleine vitesse"),
        (settings.min_duty, FAN_DUTY_RANGE, "seuil de demarrage"),
    ):
        if not low <= value <= high:
            unit = "%" if label == "seuil de demarrage" else " C"
            return f"{label} : {value}{unit} hors bornes ({low} a {high})"
    if settings.low_temp > settings.high_temp:
        return (
            f"temperature de demarrage ({settings.low_temp} C) superieure a celle de "
            f"pleine vitesse ({settings.high_temp} C)"
        )
    return None


def clamp_current(ma: int) -> int:
    """Applique les bornes du chapitre 5.6 : < 74 mA eteint le canal, max 2150 mA."""
    if ma > CURRENT_MAX_MA:
        return CURRENT_MAX_MA
    if ma < CURRENT_MIN_MA:
        return 0
    return ma
