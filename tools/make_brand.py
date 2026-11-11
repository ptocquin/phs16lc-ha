#!/usr/bin/env python3
"""Génère les assets de marque (brand/icon.png, brand/logo.png) en pur stdlib.

Motif : une LED ambre (cercle + 8 rayons) sur fond bleu ardoise — sans dépendance
(PIL non requis). Usage : python3 ha-integration/tools/make_brand.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"

BG = (24, 34, 54, 255)  # bleu ardoise foncé
AMBER = (245, 179, 1, 255)  # ambre « LED allumée"


def write_png(path: Path, w: int, h: int, pixel_fn) -> None:
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filtre None par ligne
        for x in range(w):
            raw += bytes(pixel_fn(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # RGBA 8 bits
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"{path.relative_to(ROOT)}  {w}x{h}  {len(png)} octets")


def led_icon(cx: float, cy: float, r_led: float, r_ray_in: float, r_ray_out: float, ray_w: float):
    """Pixel fn : cercle plein + 8 rayons à 45°, sinon fond."""

    def fn(x: int, y: int):
        dx, dy = x - cx, y - cy
        if math.hypot(dx, dy) <= r_led:
            return AMBER
        ang = math.atan2(dy, dx)
        a = round(ang / (math.pi / 4)) * (math.pi / 4)
        px, py = math.cos(a), math.sin(a)
        t = dx * px + dy * py  # projection sur le rayon
        perp = abs(dx * -py + dy * px)  # distance au rayon
        if r_ray_in <= t <= r_ray_out and perp <= ray_w / 2:
            return AMBER
        return BG

    return fn


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    write_png(BRAND / "icon.png", 512, 512, led_icon(256, 256, 95, 130, 185, 22))
    write_png(BRAND / "logo.png", 1024, 256, led_icon(128, 128, 62, 86, 118, 15))


if __name__ == "__main__":
    main()
