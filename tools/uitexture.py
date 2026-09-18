"""Décodage des textures UI d'Allods Online : *.(UITexture).bin.

Format : zlib( u32 zéro + u32 taille_payload + payload DXT1/DXT5 ).
Les dimensions ne sont pas stockées ; on les infère parmi les puissances de deux
en choisissant le décodage dont les lignes consécutives se ressemblent le plus.
"""
from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass

import numpy as np
from PIL import Image

BLOCK_BYTES = {b"DXT1": 8, b"DXT5": 16}


@dataclass(frozen=True)
class DecodeInfo:
    width: int
    height: int
    fourcc: str


def candidate_dims(n_blocks: int, max_ratio: int = 16) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    bw = 1
    while bw <= n_blocks:
        if n_blocks % bw == 0:
            bh = n_blocks // bw
            w, h = bw * 4, bh * 4
            if max(w, h) / min(w, h) <= max_ratio:
                out.append((w, h))
        bw *= 2
    return out


def build_dds(width: int, height: int, fourcc: bytes, payload: bytes) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000  # caps|height|width|pixelformat|linearsize
    pixel_format = struct.pack("<II4s5I", 32, 0x4, fourcc, 0, 0, 0, 0, 0)
    header = struct.pack("<7I", 124, flags, height, width, len(payload), 0, 0)
    header += b"\0" * 44 + pixel_format + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return b"DDS " + header + payload


def row_smoothness(img: Image.Image) -> float:
    a = np.asarray(img.convert("L"), dtype=np.float32)
    if a.shape[0] < 2:
        return float("inf")
    return float(np.abs(np.diff(a, axis=0)).mean())


def _try_decode(width: int, height: int, fourcc: bytes, payload: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(build_dds(width, height, fourcc, payload)))
        img.load()
        return img.convert("RGBA")
    except Exception:  # Pillow lève diverses erreurs sur un DDS incohérent
        return None


def decode_uitexture(data: bytes, dims_hint: tuple[int, int] | None = None) -> tuple[Image.Image, DecodeInfo]:
    raw = zlib.decompress(data)
    _zero, size = struct.unpack("<II", raw[:8])
    payload = raw[8:8 + size]
    if len(payload) != size:
        raise ValueError(f"payload tronqué : {len(payload)} != {size}")

    best: tuple[float, Image.Image, DecodeInfo] | None = None
    for fourcc, block_bytes in BLOCK_BYTES.items():
        if size % block_bytes:
            continue
        n_blocks = size // block_bytes
        dims = [dims_hint] if dims_hint else candidate_dims(n_blocks)
        for w, h in dims:
            if (w // 4) * (h // 4) != n_blocks:
                continue
            img = _try_decode(w, h, fourcc, payload)
            if img is None:
                continue
            score = row_smoothness(img)
            if best is None or score < best[0]:
                best = (score, img, DecodeInfo(w, h, fourcc.decode()))
    if best is None:
        raise ValueError("aucun décodage DXT possible")
    return best[1], best[2]
