"""Faux bus PHS16-LC pour les tests : remplace `PhsLink` (pyserial), sans matériel."""

from __future__ import annotations

from dataclasses import dataclass, field

from custom_components.phs16lc.phs16ctl import protocol as proto


@dataclass
class FakeSpot:
    """Une carte simulée."""

    alive: bool = True
    currents: list[int] = field(default_factory=lambda: [0] * 16)
    temps: tuple[float, float, float] = (30.0, 31.0, 32.0)


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
        if cmd == "GI":  # présence
            if spot is not None and spot.alive:
                # checksum réel (sum 8 bits) : exigé par Response.is_plausible au scan
                return proto.Response.parse(b"#GI V1.0.7 0x00001234*6F\r")
            return None
        if spot is None or not spot.alive:
            return None
        if cmd == "GP":
            vals = " ".join(str(c) for c in spot.currents)
            return proto.Response.parse(f"#GP {vals}*00\r".encode())
        if cmd == "GT":
            t = spot.temps
            return proto.Response.parse(f"#GT {t[0]} {t[1]} {t[2]}*00\r".encode())
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
