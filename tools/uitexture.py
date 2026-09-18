"""Décodage des textures UI d'Allods Online : *.(UITexture).bin.

Format : zlib( u32 zéro + u32 taille_payload + payload DXT1/DXT5 ).
Les dimensions ne sont pas stockées ; on les infère parmi les puissances de deux
en choisissant le décodage dont les pixels voisins (lignes ET colonnes
consécutives, sur les 4 canaux RGBA) se ressemblent le plus.
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


def _aspect_ratio(w: int, h: int) -> float:
    return max(w, h) / min(w, h)


def _is_better(score: float, w: int, h: int, best_score: float, best_w: int, best_h: int, tol: float = 1e-6) -> bool:
    """(score, w, h) doit-il remplacer (best_score, best_w, best_h) ?

    Les textures d'UI répétitives (bordures, barres de progression) peuvent rendre
    plusieurs découpages tout aussi « lisses » (score identique à `tol` près) :
    on départage alors par la forme la plus proche du carré, puis, à égalité de
    forme, on préfère le format paysage (largeur >= hauteur), le plus courant
    pour ces textures. À n'appliquer qu'entre candidats d'un même fourcc : deux
    fourcc différents peuvent produire un score identique sur les mêmes octets
    sans que la forme soit un indice fiable (l'un des deux est alors un artefact).
    """
    if score < best_score - tol:
        return True
    if score > best_score + tol:
        return False
    ratio, best_ratio = _aspect_ratio(w, h), _aspect_ratio(best_w, best_h)
    if ratio < best_ratio - tol:
        return True
    if ratio > best_ratio + tol:
        return False
    return w >= h and not (best_w >= best_h)


def smoothness_score(img: Image.Image) -> float:
    """Mesure la rugosité d'un décodage candidat.

    Moyenne des écarts absolus entre pixels voisins, sur les 4 canaux RGBA, à la
    fois verticalement (lignes consécutives) et horizontalement (colonnes
    consécutives). Un score bas signale un décodage plausible.

    Le score précédent ne regardait que les lignes d'une image convertie en
    niveaux de gris : un payload DXT1 relu en DXT5 peut alors sembler lisse (le
    canal alpha, bruité mais ignoré par `.convert("L")`, ne pénalisait pas ce
    mauvais décodage) et l'emporter à tort sur le DXT1 correct. Sommer sur les 4
    canaux et sur les deux axes réduit ce risque.
    """
    a = np.asarray(img.convert("RGBA"), dtype=np.float32)
    if a.shape[0] < 2 or a.shape[1] < 2:
        return float("inf")
    return float(np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean())


row_smoothness = smoothness_score  # alias conservé : tools/tests/test_uitexture.py l'utilise encore.


def _try_decode(width: int, height: int, fourcc: bytes, payload: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(build_dds(width, height, fourcc, payload)))
        img.load()
        return img.convert("RGBA")
    except Exception:  # Pillow lève diverses erreurs sur un DDS incohérent
        return None


def trim_transparent_padding(img: Image.Image) -> Image.Image:
    """Rogne les colonnes de droite et lignes du bas entièrement transparentes.

    Les textures UI d'Allods sont stockées en puissances de deux, ancrées en
    haut-gauche ; la zone utile (realWidth × realHeight du .xdb) est suivie
    d'un padding alpha=0. Le haut et la gauche ne sont jamais touchés.
    """
    if img.mode != "RGBA":
        return img
    alpha = np.asarray(img)[:, :, 3]
    rows = np.flatnonzero(alpha.max(axis=1))
    cols = np.flatnonzero(alpha.max(axis=0))
    if rows.size == 0 or cols.size == 0:
        return img
    return img.crop((0, 0, int(cols[-1]) + 1, int(rows[-1]) + 1))


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
        # Meilleur candidat pour CE fourcc : le départage forme carrée/paysage
        # (_is_better) n'a de sens qu'entre décodages du même fourcc.
        fourcc_best: tuple[float, int, int, Image.Image] | None = None
        for w, h in dims:
            if (w // 4) * (h // 4) != n_blocks:
                continue
            img = _try_decode(w, h, fourcc, payload)
            if img is None:
                continue
            score = smoothness_score(img)
            if fourcc_best is None or _is_better(score, w, h, fourcc_best[0], fourcc_best[1], fourcc_best[2]):
                fourcc_best = (score, w, h, img)
        if fourcc_best is None:
            continue
        score, w, h, img = fourcc_best
        # Entre fourcc différents, à score égal on garde le premier trouvé (DXT1
        # avant DXT5 dans BLOCK_BYTES) : la forme ne départage pas ici, elle
        # départagerait un artefact au même titre qu'un vrai résultat.
        if best is None or score < best[0]:
            best = (score, img, DecodeInfo(w, h, fourcc.decode()))
    if best is None:
        raise ValueError("aucun décodage DXT possible")
    return best[1], best[2]
