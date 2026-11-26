"""Faux bus PHS16-LC pour les tests : remplace `PhsLink` (pyserial), sans matériel."""

from __future__ import annotations

from dataclasses import dataclass, field

from custom_components.phs16lc.phs16ctl import protocol as proto


def _frame(body: str) -> bytes:
    """Trame de réponse réaliste : « body*XX<CR> » avec XX = checksum 8 bits."""
    payload = body.encode()
    return payload + b"*" + f"{sum(payload) & 0xFF:02X}".encode() + b"\r"


@dataclass
class FakeSpot:
    """Une carte simulée."""

    alive: bool = True
    currents: list[int] = field(default_factory=lambda: [0] * 16)
    temps: tuple[float, float, float] = (30.0, 31.0, 32.0)
    fan: tuple[int, int, int] = (
        40,
        60,
        30,
    )  # paramètres ventilateur @GF/@SF (dém. °C, pleine °C, seuil %)
    serial: int = 0x1234  # n° de série (provisionnement @DI/@PRG)
    programmed: bool = True  # False = SPOT neuf "non programmé" (adresse usine)


class FakePhsLink:
    """Imite `PhsLink` : même constructeur (tx_port, rx_port=None, baudrate, trace).

    Flags de panne (B2) : `fail_open` fait lever OSError au constructeur (port
    absent), `fail_io` fait lever OSError dans send() (port débranché à chaud).
    """

    instances: list[FakePhsLink] = []
    bus: dict[int, FakeSpot] = {}
    fail_open: bool = False
    fail_io: bool = False
    open_attempts: int = 0

    def __init__(
        self,
        tx_port: str,
        rx_port: str | None = None,
        baudrate: int = 115200,
        trace=None,
        dialect=None,
    ) -> None:
        type(self).open_attempts += 1
        if type(self).fail_open:
            raise OSError(19, "No such device")
        self.tx_port = tx_port
        self.rx_port = rx_port if rx_port else tx_port
        self.port = tx_port  # compat. ascendante (diagnostics)
        self.single_port = self.rx_port == self.tx_port
        self.dialect = dialect  # None = REVD (phs16-lc) ; LUMIATEC pour la gamme lumiatec
        self.closed = False
        self.sent: list[tuple[str, int, str]] = []
        FakePhsLink.instances.append(self)

    @classmethod
    def reset(cls, bus: dict[int, FakeSpot]) -> None:
        cls.instances = []
        cls.bus = bus
        cls.fail_open = False
        cls.fail_io = False
        cls.open_attempts = 0

    def send(self, cmd: str, addr: int, params: str = "", timeout: float = 0.0):
        if type(self).fail_io:
            raise OSError(19, "Device not configured")
        self.sent.append((cmd, addr, params))
        spot = self.bus.get(addr)
        if cmd == "GU":  # au moins un SPOT non programmé -> ACK
            if any(s.alive and not s.programmed for s in self.bus.values()):
                return proto.Response.parse(b"ACK*00\r")
            return None
        if cmd == "UNP":  # broadcast : tous les SPOT repassent non programmés, silence = OK
            for s in self.bus.values():
                if s.alive:
                    s.programmed = False
            return None
        if cmd == "DI":  # premier SPOT non programmé (ordre d'adresse = proximité au PC)
            for a in sorted(self.bus):
                s = self.bus[a]
                if s.alive and not s.programmed:
                    return proto.Response.parse(_frame(f"#DI V1.0.7 0x{s.serial:08x}"))
            return None
        if cmd == "PRG":  # params "0x<SN> <adresse>" : alloue l'adresse à ce SN
            parts = params.split()
            sn = int(parts[0], 16)
            new_addr = int(parts[1])
            for a in sorted(self.bus):
                s = self.bus[a]
                if s.alive and not s.programmed and s.serial == sn:
                    del self.bus[a]
                    s.programmed = True
                    self.bus[new_addr] = s
                    return proto.Response.parse(b"ACK*00\r")
            return None  # SN invalide
        if cmd == "GI":  # présence (seulement si programmé)
            if spot is not None and spot.alive and spot.programmed:
                # checksum réel (sum 8 bits) : exigé par Response.is_plausible au scan
                return proto.Response.parse(_frame(f"#GI V1.0.7 0x{spot.serial:08x}"))
            return None
        if spot is None or not spot.alive or not spot.programmed:
            return None
        if cmd == "GP":
            vals = " ".join(str(c) for c in spot.currents)
            return proto.Response.parse(f"#GP {vals}*00\r".encode())
        if cmd == "GT":
            t = spot.temps
            return proto.Response.parse(f"#GT {t[0]} {t[1]} {t[2]}*00\r".encode())
        if cmd == "GF":  # paramètres ventilateur (phs16-lc ; en lumiatec @GF = config)
            return proto.Response.parse(_frame(f"#GF {spot.fan[0]} {spot.fan[1]} {spot.fan[2]}"))
        if cmd == "SF":  # programmation ventilateur (phs16-lc)
            parts = params.split()
            if len(parts) == 3:
                spot.fan = (int(parts[0]), int(parts[1]), int(parts[2]))
            return proto.Response.parse(b"ACK*00\r")
        if cmd == "GL":  # cartes LED : type1 sn1 type2 sn2
            return proto.Response.parse(b"#GL 1 0x11 2 0x22*00\r")
        if cmd == "SP":
            spot.currents = [int(p) for p in params.split()]
            return proto.Response.parse(b"ACK*00\r")
        if cmd == "WP":
            return proto.Response.parse(b"ACK*00\r")
        return None

    def close(self) -> None:
        self.closed = True
