"""Faux bus lumiatec pour les tests HA : remplace `PhsLink` (pyserial), sans matériel.

Protocole lumiatec (fw V1.3, voir PLAN_LUMIATEC.md §0.4) : adresse décimale,
réponses « #TAG args*XX » hex + CRLF, ACK/NAK sans checksum, 16 canaux 0..15,
@SC step 0..87 (NAK 6 au-delà), @SF bits 0/1, @GE OK si bit master.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from custom_components.phs16lc.phs16ctl import protocol as proto


def _reply(body: str) -> bytes:
    payload = body.encode("ascii")
    return payload + b"*" + f"{sum(payload) & 0xFF:02X}".encode() + b"\r\n"


@dataclass
class FakeLumSpot:
    """Un luminaire lumiatec simulé."""

    alive: bool = True
    serial: int = 0x14100088
    channels: list[int] = field(default_factory=lambda: [0] * 16)  # steps 0..87
    temps: tuple[float, float, float] = (30.0, 21.4, 21.4)
    sf: int = 0  # bitmask @SF : bit0 power, bit1 master


class FakeLumLink:
    """Imite `PhsLink` avec le dialect LUMIATEC : même constructeur + `send`."""

    instances: list[FakeLumLink] = []
    bus: dict[int, FakeLumSpot] = {}
    fail_open: bool = False
    fail_io: bool = False

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
        self.port = tx_port
        self.single_port = self.rx_port == self.tx_port
        self.dialect = dialect
        self.closed = False
        self.sent: list[tuple[str, int, str]] = []
        FakeLumLink.instances.append(self)

    open_attempts: int = 0

    @classmethod
    def reset(cls, bus: dict[int, FakeLumSpot]) -> None:
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
        if spot is None or not spot.alive:
            return None
        fields = params.split()
        if cmd == "GI":
            return proto.Response.parse(_reply(f"#GI V1.3 0x{spot.serial:08X}"))
        if cmd == "GT":
            t = spot.temps
            return proto.Response.parse(_reply(f"#GT {t[0]} {t[1]} {t[2]}"))
        if cmd == "GE":
            config = "OK" if spot.sf & 2 else "ERR"
            return proto.Response.parse(_reply(f"#GE {config} OxFFFF"))
        if cmd == "GF":
            return proto.Response.parse(_reply(f"#GF Ox{spot.sf:08X}"))
        if cmd == "GS":
            return proto.Response.parse(_reply("#GS 1000"))
        if cmd == "GB":
            return proto.Response.parse(_reply("#GB 0 " + "00" * 104))
        if cmd == "GC":
            ch = int(fields[0])
            if not 0 <= ch < 16:
                return proto.Response.parse(b"NAK 4\r\n")
            return proto.Response.parse(_reply(f"#GC {ch} {spot.channels[ch]} 0 200"))
        if cmd == "SC":
            if len(fields) != 4:
                return proto.Response.parse(b"NAK 3\r\n")
            ch, step = int(fields[0]), int(fields[1])
            if not 0 <= ch < 16 or not 0 <= step <= 200:
                return proto.Response.parse(b"NAK 4\r\n")
            if step > 87:
                return proto.Response.parse(b"NAK 6\r\n")
            spot.channels[ch] = step
            return proto.Response.parse(b"ACK\r\n")
        if cmd == "SF":
            bm = int(fields[0])
            if bm & ~0b11:
                return proto.Response.parse(b"NAK 4\r\n")
            spot.sf = bm
            return proto.Response.parse(b"ACK\r\n")
        if cmd == "SS":
            return proto.Response.parse(b"ACK\r\n")
        if cmd == "SV":
            return proto.Response.parse(b"ACK\r\n")
        return proto.Response.parse(b"NAK 2\r\n")

    def close(self) -> None:
        self.closed = True
