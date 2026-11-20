"""Transport serie RS-485 full duplex vers le reseau de SPOT.

Le PC est maitre : chaque commande est emise puis on attend au plus `timeout`
secondes une reponse terminee par <CR>.  L'absence de reponse n'est pas une
erreur -- c'est un element du protocole (fin d'enumeration, SPOT deja
programme, ...), d'ou le retour `None` plutot qu'une exception.

La ligne est full duplex (deux paires differentielles A/B).  Deux cablages :

- **un seul convertisseur** USB/RS-422 (ex. FTDI USB-RS422-WE) : les deux
  paires passent par un unique port serie, emission et reception partagent
  ce port ;
- **deux convertisseurs** half duplex (ex. boitier fabricant avec deux
  USB-RS485-WE) : un port pour la paire d'emission (TX), un autre pour la
  paire de reception (RX).

`PhsLink` gere les deux : on lui passe un port d'emission et un port de
reception, identiques ou distincts.  Le reste du programme est indifferent.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import serial
from serial.tools import list_ports

from .protocol import CR, REVD, Dialect, Response, build_frame

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
    """Lien serie 115200 8N1 full duplex vers la ligne de SPOT.

    `tx_port` porte l'emission, `rx_port` la reception.  Les deux peuvent etre
    le meme peripherique (un seul convertisseur full duplex) ou deux
    peripheriques distincts (un convertisseur half duplex par paire A/B).
    """

    def __init__(
        self,
        tx_port: str,
        rx_port: str | None = None,
        baudrate: int = BAUDRATE,
        trace: Callable[[str], None] | None = None,
        dialect: Dialect | None = None,
    ) -> None:
        rx_port = rx_port if rx_port is not None else tx_port
        self.tx_port = tx_port
        self.rx_port = rx_port
        self.trace = trace
        #: Format de trame ; `None` = REVD (PHS16-LC), byte-identique à l'historique.
        self.dialect = dialect if dialect is not None else REVD
        self._tx = serial.Serial(
            port=tx_port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0,
        )
        if rx_port == tx_port:
            # Un seul convertisseur full duplex : le meme port lit et ecrit.
            self._rx = self._tx
        else:
            self._rx = serial.Serial(
                port=rx_port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
            )

    @property
    def single_port(self) -> bool:
        """Vrai si emission et reception partagent le meme peripherique."""
        return self._rx is self._tx

    @property
    def port(self) -> str:
        """Port d'emission (compat. ascendante : `PhsLink(port).port`)."""
        return self.tx_port

    def close(self) -> None:
        if self._tx.is_open:
            self._tx.close()
        # `_rx is _tx` en montage a un port : ne pas fermer deux fois.
        if self._rx is not self._tx and self._rx.is_open:
            self._rx.close()

    def __enter__(self) -> "PhsLink":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def send(self, cmd: str, addr: int, params: str = "", timeout: float = 0.0) -> Response | None:
        """Emet une commande et retourne la reponse, ou None sur timeout.

        `timeout=0` correspond aux commandes qui n'attendent aucune reponse
        (@GO du bootloader) : la trame est emise et la fonction rend la main.
        """
        frame = build_frame(cmd, addr, params, dialect=self.dialect)
        # Purge du tampon de reception avant emission : c'est le port RX qui
        # recoit (en montage a un port, c'est le meme objet que le TX).
        self._rx.reset_input_buffer()
        self._tx.write(frame)
        self._tx.flush()
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

        Avec `dialect.echo_filter` (bus half-duplex dont l'adaptateur renvoie
        l'écho de notre propre trame) : une trame reçue commençant par '@' est
        jetée et la lecture continue jusqu'à la vraie réponse. Inactif par
        défaut (REVD) : aucun changement pour PHS16-LC.
        """
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._rx.timeout = remaining
            chunk = self._rx.read_until(CR, size=512)
            if chunk:
                buffer += chunk
                if CR in buffer:
                    if self.dialect.echo_filter and buffer.lstrip(b"\x00").startswith(b"@"):
                        buffer = bytearray()  # écho de notre trame : on jette, on continue
                        continue
                    return bytes(buffer)
