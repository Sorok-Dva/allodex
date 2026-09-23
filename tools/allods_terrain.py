"""Terrain des cartes d'Allods Online (client 17.0) : `<région>_terrainDump.bin`.

Format établi sur les données (`Ferris4`, région 5_4), recoupé **au centimètre** avec la carte
de hauteurs de l'arbre serveur 7.0 (`5_4_terrain.bin`, carreaux de 8 × 8 hauteurs sur une grille
de 33 × 33, marge d'un mètre) :

* fichier `read_chunks`, bloc 0 ; entête de pointeurs relatifs `(décalage depuis le champ, nombre)` :
  `+0x08` jeux de calques (9 o : 4 octets de drapeaux, 3 indices de calque, `0xFF` = aucun),
  `+0x10` carreaux de 32 m (32 o : centre et demi-taille de la boîte, puis sous-carreaux),
  `+0x18`, `+0x20` données par carreau (non utilisées ici) ;
* sous-carreau de 8 m (40 o) : quatre couples `(décalage, nombre)` — indices du niveau de détail
  grossier (`u8`), indices du niveau fin (`u8`, triangles), sommets, passes —, puis la place du
  sous-carreau dans la région (`u16 x, u16 y`, en sous-carreaux), le nombre de sommets (`u16`) et
  la couche (`u16` : `FerrisRaid` superpose deux sols dans une même région) ;
* sommet : 4 octets `(nx, ny, nz, g)` — normale (octets centrés sur 127,5) et `g` = indice dans la
  grille 9 × 9 du sous-carreau (`x = 8·sx + g // 9`, `y = 8·sy + g % 9`, en mètres) —, puis, après
  tous les sommets, une hauteur `f32` par sommet (maillage adaptatif : 66 des 81 points) ;
* passe (6 o) : `u16` premier sommet dans la région, `u16` jeu de calques, `u8 c`, `u8 d` : le bloc de
  8 × 8 texels du `SplatMap` qui porte ses poids (lignes `8c…8c+7`, colonnes `8d…8d+7`).

Calques : `TerraLayers` de la région (`MapRegion +0x98`) : entrées de 376 o à partir de `+0x230`
(texture, taille de répétition en mètres en `+0x08`) ; l'indice d'un jeu de calques est décalé
d'un (le 0 du `.xdb` 7.0 est vide). Poids : `SplatMap_0` de la région (256², R5G6B5) est un **atlas de
blocs** de 8 × 8 texels, un par passe (`c`, `d`) : la ligne `i` du bloc est à `x = 8·sx + i·8/7`, la
colonne `j` à `y = 8·sy + j·8/7` — les blocs de deux sous-carreaux voisins partagent leur bord à
l'identique (écart moyen 0,0000 sur `Ferris4`, 229 paires). R, G, B sont les poids des trois calques
du jeu de la passe dans l'ordre ; une passe unique somme à 1, deux passes (la seconde marquée par le
4ᵉ octet de drapeaux du jeu) somment à 1 ensemble (≈ 0,65 + 0,35) ; un jeu à un seul calque pointe le
bloc (0, 0), plein en R.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

REGION_SIZE = 256.0
LAYER_FIRST = 0x230
LAYER_STRIDE = 376
LAYER_TILING = 0x08


@dataclass
class Patch:
    """Sous-carreau de 8 m : sommets (mètres, locaux à la région), normales, triangles."""
    sx: int
    sy: int
    points: np.ndarray          # (n, 3) x, y, z
    normals: np.ndarray         # (n, 3)
    triangles: np.ndarray       # (m, 3) indices locaux
    coarse: np.ndarray          # (k, 3) niveau de détail grossier
    passes: list[tuple[int, int, int, int]]   # (premier sommet, jeu de calques, bloc c, bloc d)
    level: int = 0                  # couche (`FerrisRaid` : deux sols superposés dans une région)


def _selfptr(raw: bytes, off: int) -> tuple[int, int]:
    value, count = struct.unpack_from("<II", raw, off)
    return off + value, count


def parse_terrain_dump(raw: bytes) -> tuple[list[tuple[int, ...]], list[Patch]]:
    """Bloc 0 décompressé d'un `terrainDump.bin` → (jeux de calques, sous-carreaux)."""
    sets_at, sets_n = _selfptr(raw, 0x08)
    layer_sets = []
    for k in range(sets_n):
        ids = raw[sets_at + 9 * k + 4:sets_at + 9 * k + 7]
        layer_sets.append(tuple(i for i in ids if i != 0xFF))
    tiles_at, tiles_n = _selfptr(raw, 0x10)
    patches: list[Patch] = []
    for t in range(tiles_n):
        base = tiles_at + 32 * t
        sub_at, sub_n = _selfptr(raw, base + 24)
        for k in range(sub_n):
            o = sub_at + 40 * k
            (c_at, c_n), (f_at, f_n), (v_at, _), (p_at, p_n) = (_selfptr(raw, o + 8 * j) for j in range(4))
            where, packed = struct.unpack_from("<II", raw, o + 32)
            n, level = packed & 0xFFFF, packed >> 16      # niveau : couches de terrain superposées
            sx, sy = where & 0xFFFF, where >> 16
            quad = np.frombuffer(raw, np.uint8, 4 * n, v_at).reshape(n, 4)
            z = np.frombuffer(raw, "<f4", n, v_at + 4 * n).astype(np.float64)
            g = quad[:, 3].astype(np.int64)
            points = np.column_stack([8 * sx + g // 9, 8 * sy + g % 9, z]).astype(np.float64)
            normals = (quad[:, :3].astype(np.float64) - 127.5) / 127.5
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
            fine = np.frombuffer(raw, np.uint8, f_n, f_at)
            coarse = np.frombuffer(raw, np.uint8, c_n, c_at)
            passes = [struct.unpack_from("<HHBB", raw, p_at + 6 * j) for j in range(p_n)]
            patches.append(Patch(sx, sy, points, normals, fine[: len(fine) // 3 * 3].reshape(-1, 3).astype(np.int64),
                                 coarse[: len(coarse) // 3 * 3].reshape(-1, 3).astype(np.int64), passes, level))
    return layer_sets, patches


def splat_weights(raw: bytes) -> np.ndarray:
    """`SplatMap_0` (256 × 256 × R5G6B5) → poids (256, 256, 3) des calques d'une passe."""
    u = np.frombuffer(raw, "<u2", 256 * 256).reshape(256, 256).astype(np.float64)
    w = np.stack([np.floor(u / 2048) / 31, (np.floor(u / 32) % 64) / 63, (u % 32) / 31], -1)
    return w


def terrain_layers(db, cat, terra: int | None) -> list[tuple[str | None, float]]:
    """Calques de `TerraLayers` : (nom de la texture, taille de répétition en mètres)."""
    out: list[tuple[str | None, float]] = []
    if terra is None:
        return out
    for k in range(64):
        entry = terra + LAYER_FIRST + LAYER_STRIDE * k
        tex = db.ptr(entry)
        if tex is None and k > 40:
            break
        name = cat.name(db.binary_ref(tex)) if tex is not None and db.vtype(tex) == "Texture" else None
        tiling = db.f32(entry + LAYER_TILING) if name else 0.0
        out.append((name, tiling if tiling > 0 else 30.0))
    return out


def region_patches(get, map_name: str, region_path: str) -> tuple[list[tuple[int, ...]], list[Patch]] | None:
    """Terrain d'une région (`Maps/X/000_000/5_4_MapRegion.xdb` → `…/5_4_terrainDump.bin`)."""
    from tools.extract_menu_scene import read_chunks
    raw = get(region_path.replace("_MapRegion.xdb", "_terrainDump.bin"))
    if not raw:
        return None
    chunk = read_chunks(raw).get(0)
    if not chunk or len(chunk) < 0x40:
        return None
    return parse_terrain_dump(chunk)


def pass_weights(splat: np.ndarray | None, patch: Patch, block: tuple[int, int]) -> np.ndarray:
    """Poids (n, 3) des trois calques d'une passe aux sommets du sous-carreau : lecture bilinéaire de
    son bloc de 8 × 8 texels (texel `i` à `i·8/7` m du coin), sans bloc (pas de `SplatMap`) : (1, 0, 0)."""
    n = len(patch.points)
    if splat is None:
        out = np.zeros((n, 3))
        out[:, 0] = 1.0
        return out
    c, d = block
    gx = np.clip(patch.points[:, 0] - 8 * patch.sx, 0, 8) * 7.0 / 8.0
    gy = np.clip(patch.points[:, 1] - 8 * patch.sy, 0, 8) * 7.0 / 8.0
    i0, j0 = np.floor(gx).astype(int).clip(0, 6), np.floor(gy).astype(int).clip(0, 6)
    fx, fy = (gx - i0)[:, None], (gy - j0)[:, None]
    rows, cols = 8 * c + i0, 8 * d + j0
    w00, w10 = splat[rows, cols], splat[rows + 1, cols]
    w01, w11 = splat[rows, cols + 1], splat[rows + 1, cols + 1]
    return (w00 * (1 - fx) + w10 * fx) * (1 - fy) + (w01 * (1 - fx) + w11 * fx) * fy


def region_splat(get, region_path: str) -> np.ndarray | None:
    from tools.extract_menu_scene import read_chunks
    raw = get(region_path.replace("_MapRegion.xdb", "_SplatMap_0.(Texture).bin"))
    chunk = read_chunks(raw).get(0) if raw else None
    return splat_weights(chunk) if chunk and len(chunk) >= 256 * 256 * 2 else None
