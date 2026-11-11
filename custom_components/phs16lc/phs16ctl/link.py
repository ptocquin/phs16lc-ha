"""Transport serie RS-485 vers le reseau de SPOT.

Le PC est maitre : chaque commande est emise puis on attend au plus `timeout`
secondes une reponse terminee par <CR>.  L'absence de reponse n'est pas une
erreur -- c'est un element du protocole (fin d'enumeration, SPOT deja
programme, ...), d'ou le retour `None` plutot qu'une exception.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import serial
from serial.tools import list_ports

from .protocol import CR, Response, build_frame

BAUDRATE = 115200

# Timeouts (secondes) repris un a un de MainWindow::sendCommand() du projet Qt.
T_GU = 0.2
T_GI = 0.2
T_DI = 0.2
T_UNP = 0.5
T_PRG = 0.5
T_GP = 0.5
T_SP = 0.5
T_GT = 0.5
T_GL = 0.5
T_WP = 0.5
# @GF est nettement plus lent que les autres lectures cote firmware.
T_GF = 1.5
T_SF = 0.5


def available_ports() -> list[tuple[str, str]]:
    """Liste des ports serie detectes : [(device, description), ...]."""
    return [(p.device, p.description or "") for p in list_ports.comports()]


class PhsLink:
    """Lien serie 115200 8N1 vers la ligne de SPOT."""

    def __init__(
        self,
        port: str,
        baudrate: int = BAUDRATE,
        trace: Callable[[str], None] | None = None,
    ) -> None:
        self.port = port
        self.trace = trace
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0,
        )

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "PhsLink":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def send(self, cmd: str, addr: int, params: str = "", timeout: float = 0.0) -> Response | None:
        """Emet une commande et retourne la reponse, ou None sur timeout.

        `timeout=0` correspond aux commandes qui n'attendent aucune reponse
        (@GO du bootloader) : la trame est emise et la fonction rend la main.
        """
        frame = build_frame(cmd, addr, params)
        self._serial.reset_input_buffer()
        self._serial.write(frame)
        self._serial.flush()
        if self.trace:
            self.trace(f"TX {frame!r}")
        if timeout <= 0:
            return None

        data = self._read_frame(timeout)
        if data is None:
            if self.trace:
                self.trace(f"RX <timeout {timeout:.2f}s>")
            return None
        resp = Response.parse(data)
        if self.trace:
            self.trace(f"RX {data!r}")
        return resp

    def _read_frame(self, timeout: float) -> bytes | None:
        """Accumule les octets jusqu'au <CR>, ou None si le delai expire.

        Le timeout porte sur la trame complete et non sur chaque octet, pour
        qu'une reponse partielle ne puisse pas prolonger l'attente indefiniment.
        """
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._serial.timeout = remaining
            chunk = self._serial.read_until(CR, size=512)
            if chunk:
                buffer += chunk
                if CR in buffer:
                    return bytes(buffer)
