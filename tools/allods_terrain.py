"""Terrain des cartes d'Allods Online (client 17.0) : `<région>_terrainDump.bin`.

Format établi sur les données (`Ferris4`, région 5_4), recoupé **au centimètre** avec la carte
de hauteurs de l'arbre serveur 7.0 (`5_4_terrain.bin`, carreaux de 8 × 8 hauteurs sur une grille
de 33 × 33, marge d'un mètre) :

* fichier `read_chunks`, bloc 0 ; entête de pointeurs relatifs `(décalage depuis le champ, nombre)` :
  `+0x00` tampons de sommets (4 o : `u16` taille, `u8` « complexe » — 12 o par sommet au lieu de 8,
  la hauteur de la surface opposée en plus —, non utilisés ici), `+0x08` jeux de calques (9 o :
  4 octets de drapeaux — complexe, `isXYZTextured`, couche, additive —, 3 indices de calque, `0xFF`
  = aucun, `u8` tampon de sommets, `u8` **numéro du `SplatMap_N`** qui porte les poids),
  `+0x10` carreaux de 32 m (32 o : centre et demi-taille de la boîte, puis sous-carreaux), puis,
  non utilisés ici, `+0x18` occulteurs, `+0x20` herbe, `+0x28` matériaux et `+0x30` carreaux d'eau ;
* sous-carreau de 8 m (40 o) : quatre couples `(décalage, nombre)` — indices du niveau de détail
  grossier (`u8`), indices du niveau fin (`u8`, triangles), sommets, passes —, puis la place du
  sous-carreau dans la région (`u16 x, u16 y`, en sous-carreaux), le nombre de sommets (`u16`) et
  la couche (`u16` : `FerrisRaid` superpose deux sols dans une même région) ;
* sommet : 4 octets `(nx, ny, nz, g)` — normale (octets centrés sur 127,5) et `g` = indice dans la
  grille 9 × 9 du sous-carreau (`x = 8·sx + g // 9`, `y = 8·sy + g % 9`, en mètres) —, puis, après
  tous les sommets, une hauteur `f32` par sommet (maillage adaptatif : 66 des 81 points) ;
* passe (6 o) : `u16` premier sommet dans le tampon, `u16` jeu de calques, `u8 c`, `u8 d` : le bloc de
  8 × 8 texels du `SplatMap_N` de son jeu qui porte ses poids (lignes `8c…8c+7`, colonnes `8d…8d+7`).

Structures recoupées avec les patterns ImHex de Paulus (`tools/reverse/terrain.hexpat`,
`splatmap.hexpat`).

Calques : `TerraLayers` de la région (`MapRegion +0x98`) : 256 entrées de 376 o à partir de `+0xB0`
(texture en `+0x08`), indexées directement par les identifiants des jeux de calques (l'entrée 0 est
vide en 7.0 et dans `Ferris4`, pas partout). Les calques n'ont **pas** de répétition propre : le
vertex shader du terrain (`Material/terrain-dx11.bin`, les 24 variantes du sol) écrit
`TEXCOORD0 = −position · 0,125` (position dans la région, en mètres) et les pixel shaders
échantillonnent `tex0…tex3` à ces coordonnées (plans xy, xz, yz), sans constante par calque : toute
texture de calque se répète tous les **8 m**, un sous-carreau (`LAYER_REPEAT`, `layer_uv`). Les
flottants `+0x10` (30, 40…) et `+0x18` sont les exposants spéculaires, recoupés champ à champ avec
le `layers.xdb` 7.0 de `Kania` : `+0x10` `DirectionalExponent`, `+0x14`
`DirectionalSpeculatLightColor`, `+0x18` `EyeExponent`, `+0x1C` `EyeSpecularLightColor`, `+0x20`
`LayerColor`. Poids : les `SplatMap_0…2` de la région (256², R5G6B5) sont des
**atlas de blocs** de 8 × 8 texels, un par passe (`c`, `d`), distribués dans l'ordre de dessin (le
`_0` plein, 1 024 blocs, puis le `_1`, puis le `_2`) ; le jeu de calques nomme le sien — lu dans le
`_0` par erreur, un bloc du `_1` met du poids sur un calque absent (63 % des passes de
`FerrisRaid`, 0 % dans le bon atlas) : la ligne `i` du bloc est à `x = 8·sx + i·8/7`, la
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
LAYER_TABLE = 0x30        # vecteur des entrées de calque, la première en `+0xB0`
LAYER_ENTRY0 = 0xB0
LAYER_STRIDE = 376
LAYER_TEXTURE = 0x08
# Répétition des textures de calque, fixée par le shader du terrain (`TEXCOORD0 = −position / 8`).
LAYER_REPEAT = 8.0
SPLAT_MAPS = 3
# Touffes d'herbe d'un calque (`foliage0…3`, 72 o chacune depuis `+0x48` de l'entrée ; recoupé sur
# `Ferris4` 7.0 ↔ 17.0, calque 21 `ZC10_Grass_04`) : `bottom` (hauteur, décalage, largeur) `+0x00`,
# `maxScale` `+0x18`, `minScale` `+0x1C`, `numLeaves` `+0x20`, `probability` `+0x24`, texture
# (`TextureSingleElement`) `+0x28`, `top` `+0x34`.
LAYER_FOLIAGE = 0x48
FOLIAGE_STRIDE = 0x48
FOLIAGES = 4
TERRA_GRASS_ATLAS = 0x60      # `TextureAtlas` : `+0x28` texture, `+0x30` sources (48 o)
ATLAS_TEXTURE = 0x28
ATLAS_SOURCES = 0x30
ATLAS_SOURCE_STRIDE = 48      # `+0x08` élément, `+0x10` largeur, `+0x14` x, `+0x20` y (hauteur `+0x04`)
TERRA_WATER_LAYERS = 0x90     # 256 entrées de 136 o
WATER_LAYER_STRIDE = 136


@dataclass
class Patch:
    """Sous-carreau de 8 m : sommets (mètres, locaux à la région), normales, triangles."""
    sx: int
    sy: int
    points: np.ndarray          # (n, 3) x, y, z
    normals: np.ndarray         # (n, 3)
    triangles: np.ndarray       # (m, 3) indices locaux
    coarse: np.ndarray          # (k, 3) niveau de détail grossier
    passes: list[tuple[int, int, int, int, int]]   # (premier sommet, jeu de calques, bloc c, bloc d, SplatMap_N)
    level: int = 0                  # couche (`FerrisRaid` : deux sols superposés dans une région)


def _selfptr(raw: bytes, off: int) -> tuple[int, int]:
    value, count = struct.unpack_from("<II", raw, off)
    return off + value, count


def parse_terrain_dump(raw: bytes) -> tuple[list[tuple[int, ...]], list[Patch]]:
    """Bloc 0 décompressé d'un `terrainDump.bin` → (jeux de calques, sous-carreaux)."""
    sets_at, sets_n = _selfptr(raw, 0x08)
    layer_sets, splat_of_set = [], []
    for k in range(sets_n):
        ids = raw[sets_at + 9 * k + 4:sets_at + 9 * k + 7]
        layer_sets.append(tuple(i for i in ids if i != 0xFF))
        splat_of_set.append(raw[sets_at + 9 * k + 8])
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
            passes = [(*link, splat_of_set[link[1]] if link[1] < sets_n else 0)
                      for link in (struct.unpack_from("<HHBB", raw, p_at + 6 * j) for j in range(p_n))]
            patches.append(Patch(sx, sy, points, normals, fine[: len(fine) // 3 * 3].reshape(-1, 3).astype(np.int64),
                                 coarse[: len(coarse) // 3 * 3].reshape(-1, 3).astype(np.int64), passes, level))
    return layer_sets, patches


@dataclass
class Occluder:
    """Occulteur d'un carreau de 32 m (56 o) : `xmin` (4 `f32`), `xmax` (4 `f32`, `-FLT_MAX` dans
    toutes les régions lues), boîte (centre, demi-taille ; demi-hauteur 512 m)."""
    xmin: tuple[float, float, float, float]
    xmax: tuple[float, float, float, float]
    center: tuple[float, float, float]
    extents: tuple[float, float, float]


@dataclass
class GrassSet:
    """Herbe d'un calque dans un carreau de 32 m : `layer` = entrée de `TerraLayers` (calque du sol),
    `foliage` = numéro de sa touffe (`foliage0…3`), `flag` = bit 7 de l'octet (les deux jeux, avec
    et sans, portent les mêmes places), `xy` = places au mètre dans le carreau (n, 2)."""
    layer: int
    foliage: int
    flag: bool
    xy: np.ndarray


@dataclass
class GrassPatch:
    i: int                      # carreau de 32 m (x = 32·i)
    j: int
    center: tuple[float, float, float]
    extents: tuple[float, float, float]
    sets: list[GrassSet]


@dataclass
class WaterPatch:
    """Eau d'un carreau de 32 m (84 o) : hauteurs de la surface et vitesses aux quatre coins (`Vec4`),
    éléments `(x, y, i, j)` : carrés de 8 m à `(i, j)` mètres du coin `(ox, oy)` du carreau — `x, y` :
    numéro d'ordre continu (32 par ligne) sur toute la région —, matériau (`WaterMaterial`) et type
    d'eau (entrée de `TerraLayers.waterLayers`)."""
    ox: int
    oy: int
    center: tuple[float, float, float]
    extents: tuple[float, float, float]
    height: tuple[float, float, float, float]
    speed_x: tuple[float, float, float, float]
    speed_y: tuple[float, float, float, float]
    elements: np.ndarray        # (n, 4) u8 : x, y, i, j
    material: int
    water: int


@dataclass
class TerrainExtras:
    buffers: list[tuple[int, bool]]                      # tampons de sommets : (taille, complexe)
    occluders: list[Occluder]
    grass: list[GrassPatch]
    water_materials: list[tuple[bool, int, int]]         # (complexe, texture, sommets)
    water: list[WaterPatch]


def parse_terrain_extras(raw: bytes) -> TerrainExtras:
    """Blocs du `terrainDump` hors du sol (patterns de Paulus, `tools/reverse/terrain.hexpat`) :
    `+0x00` tampons de sommets (4 o), `+0x18` occulteurs (56 o), `+0x20` herbe (carreaux de 36 o :
    boîte, vecteur de jeux de 12 o `(u8 calque, u8 touffe | 0x80, 2 o, vecteur de (u8 x, u8 y))`,
    `u16 i, j`), `+0x28` matériaux d'eau (4 o : `u8` complexe, `u8` texture, `u16` sommets),
    `+0x30` carreaux d'eau (84 o : boîte, `Vec4` hauteur, vitesses x et y, vecteur d'éléments de 4 o,
    `u8 x, y` du coin en mètres, `u8` matériau, `u8` type d'eau)."""
    def vec(off: int) -> tuple[int, int]:
        return _selfptr(raw, off) if len(raw) >= off + 8 else (0, 0)
    b_at, b_n = vec(0x00)
    buffers = [(struct.unpack_from("<H", raw, b_at + 4 * k)[0], bool(raw[b_at + 4 * k + 2])) for k in range(b_n)]
    o_at, o_n = vec(0x18)
    occluders = []
    for k in range(o_n):
        f = struct.unpack_from("<14f", raw, o_at + 56 * k)
        occluders.append(Occluder(f[0:4], f[4:8], f[8:11], f[11:14]))
    g_at, g_n = vec(0x20)
    grass = []
    for k in range(g_n):
        o = g_at + 36 * k
        box = struct.unpack_from("<6f", raw, o)
        s_at, s_n = _selfptr(raw, o + 24)
        i, j = struct.unpack_from("<HH", raw, o + 32)
        sets = []
        for q in range(s_n):
            so = s_at + 12 * q
            xy_at, xy_n = _selfptr(raw, so + 4)
            xy = np.frombuffer(raw, np.uint8, 2 * xy_n, xy_at).reshape(-1, 2).astype(np.int64)
            sets.append(GrassSet(raw[so], raw[so + 1] & 0x7F, bool(raw[so + 1] & 0x80), xy))
        grass.append(GrassPatch(i, j, box[:3], box[3:], sets))
    m_at, m_n = vec(0x28)
    materials = [(bool(raw[m_at + 4 * k]), raw[m_at + 4 * k + 1], struct.unpack_from("<H", raw, m_at + 4 * k + 2)[0])
                 for k in range(m_n)]
    w_at, w_n = vec(0x30)
    water = []
    for k in range(w_n):
        o = w_at + 84 * k
        f = struct.unpack_from("<18f", raw, o)
        e_at, e_n = _selfptr(raw, o + 72)
        elements = np.frombuffer(raw, np.uint8, 4 * e_n, e_at).reshape(-1, 4).astype(np.int64)
        ox, oy, material, kind = raw[o + 80:o + 84]
        water.append(WaterPatch(ox, oy, f[0:3], f[3:6], f[6:10], f[10:14], f[14:18], elements, material, kind))
    return TerrainExtras(buffers, occluders, grass, materials, water)


def splat_weights(raw: bytes) -> np.ndarray:
    """`SplatMap_0` (256 × 256 × R5G6B5) → poids (256, 256, 3) des calques d'une passe."""
    u = np.frombuffer(raw, "<u2", 256 * 256).reshape(256, 256).astype(np.float64)
    w = np.stack([np.floor(u / 2048) / 31, (np.floor(u / 32) % 64) / 63, (u % 32) / 31], -1)
    return w


def terrain_layers(db, cat, terra: int | None) -> list[str | None]:
    """Calques de `TerraLayers`, indexés par l'identifiant des jeux de calques : nom de la texture.
    Le tableau (vecteur en `+0x30`, entrées de 376 o, texture en `+0x08`) a 256 entrées fixes, avec
    des trous ; l'entrée 0 compte : `Inst_ZoneContested12_Start` la nomme et 1 629 de ses jeux y
    renvoient, comme aux calques 54 à 121 — la liste commençait à l'entrée 1 et s'arrêtait au premier
    trou après la 40ᵉ, ces sous-carreaux prenaient un calque sans texture. La répétition ne se lit
    pas ici : elle est la même pour tous (`layer_uv`)."""
    out: list[str | None] = []
    if terra is None:
        return out
    table = db.vec(terra + LAYER_TABLE)
    first, count = (table[0], table[1] // LAYER_STRIDE) if table else (terra + LAYER_ENTRY0, 65)
    for k in range(count):
        entry = first + LAYER_STRIDE * k
        tex = db.ptr(entry + LAYER_TEXTURE)
        out.append(cat.name(db.binary_ref(tex)) if tex is not None and db.vtype(tex) == "Texture" else None)
    return out


def layer_uv(xy: np.ndarray) -> np.ndarray:
    """Coordonnées de texture d'un calque, comme le shader du terrain : `−(x, y) / 8` (mètres, dans
    la région ou la carte : les régions font 32 répétitions, la phase ne change pas)."""
    return (-np.asarray(xy, np.float64) / LAYER_REPEAT).astype(np.float32)


def _dump_chunk(get, region_path: str) -> bytes | None:
    from tools.extract_menu_scene import read_chunks
    raw = get(region_path.replace("_MapRegion.xdb", "_terrainDump.bin"))
    if not raw:
        return None
    chunk = read_chunks(raw).get(0)
    return chunk if chunk and len(chunk) >= 0x38 else None


@dataclass
class Foliage:
    """Touffe d'herbe d'un calque (`TerraLayers.Layers[k].foliageN`)."""
    element: int | None               # `TextureSingleElement` (place dans l'atlas d'herbe)
    probability: int
    leaves: int
    min_scale: float
    max_scale: float
    top: tuple[float, float, float]      # hauteur, décalage, largeur
    bottom: tuple[float, float, float]


def terrain_foliage(db, terra: int | None) -> list[list[Foliage]]:
    """Touffes des 256 calques de `TerraLayers`, indexées comme `terrain_layers` puis par numéro de
    touffe (octet `grassSubType` des carreaux d'herbe du `terrainDump`)."""
    if terra is None:
        return []
    table = db.vec(terra + LAYER_TABLE)
    if not table:
        return []
    out = []
    for k in range(table[1] // LAYER_STRIDE):
        entry = table[0] + LAYER_STRIDE * k
        row = []
        for f in range(FOLIAGES):
            o = entry + LAYER_FOLIAGE + FOLIAGE_STRIDE * f
            row.append(Foliage(db.ptr(o + 0x28), db.i32(o + 0x24), db.i32(o + 0x20), db.f32(o + 0x1C), db.f32(o + 0x18),
                               tuple(round(v, 4) for v in db.floats(o + 0x34, 3)),
                               tuple(round(v, 4) for v in db.floats(o, 3))))
        out.append(row)
    return out


def foliage_atlas(db, cat, terra: int | None) -> tuple[str | None, dict[int, tuple[int, int, int, int]]]:
    """Atlas des textures d'herbe de la carte (`TerraLayers +0x60`, `Maps/<carte>/layers.(Texture)`) :
    nom de la texture et place `(x, y, largeur, hauteur)` en pixels de chaque `TextureSingleElement`
    (recoupé sur `layers.(TextureAtlas).xdb` 7.0 de `Ferris4` : mêmes éléments, repacés en colonne)."""
    atlas = db.ptr(terra + TERRA_GRASS_ATLAS) if terra is not None else None
    if atlas is None or db.vtype(atlas) != "TextureAtlas":
        return None, {}
    tex = db.ptr(atlas + ATLAS_TEXTURE)
    name = cat.name(db.binary_ref(tex)) if tex is not None and db.vtype(tex) == "Texture" else None
    rects = {}
    for e in db.elements(atlas + ATLAS_SOURCES, ATLAS_SOURCE_STRIDE):
        element = db.ptr(e + 0x08)
        if element is not None:
            rects[element] = (db.i32(e + 0x14), db.i32(e + 0x20), db.i32(e + 0x10), db.i32(e + 0x04))
    return name, rects


WATER_TEXTURES = {"bump": 0x20, "fresnelDown": 0x28, "fresnelUp": 0x30, "fresnelUpWaterWaves": 0x38,
                  "wave": 0x58, "waveBump": 0x68}


def water_layers(db, cat, terra: int | None) -> list[dict]:
    """Types d'eau de `TerraLayers.waterLayers` (256 × 136 o), recoupés sur les `layers.xdb` 7.0 de
    `Ferris4` et `Inst_ZoneContested12_Start` : nom `+0x08`, textures (`WATER_TEXTURES`), `waterAlpha`
    `+0x48`, `waterReflectionContribution` `+0x4C`, `waterSpecularCoeff` `+0x50`, `waterSpeedMultiply`
    `+0x54` (entier), `waveHeight` `+0x70`, `waveReflectionContribution` `+0x74`, `waveSpeedMultiply`
    `+0x78`, `waveWidth` `+0x7C` ; `waterAdditionalColor` (`+0x44`, ARGB) nul partout."""
    table = db.vec(terra + TERRA_WATER_LAYERS) if terra is not None else None
    if not table:
        return []
    out = []
    for k in range(table[1] // WATER_LAYER_STRIDE):
        e = table[0] + WATER_LAYER_STRIDE * k
        textures = {}
        for key, off in WATER_TEXTURES.items():
            t = db.ptr(e + off)
            textures[key] = cat.name(db.binary_ref(t)) if t is not None and db.vtype(t) == "Texture" else None
        out.append({"name": db.string(e + 0x08), "textures": textures, "addColor": db.u32(e + 0x44),
                    "alpha": round(db.f32(e + 0x48), 4), "reflection": round(db.f32(e + 0x4C), 4),
                    "specular": round(db.f32(e + 0x50), 4), "speed": db.i32(e + 0x54),
                    "waveHeight": round(db.f32(e + 0x70), 4), "waveReflection": round(db.f32(e + 0x74), 4),
                    "waveSpeed": db.i32(e + 0x78), "waveWidth": round(db.f32(e + 0x7C), 4)})
    return out


def grid_samples(patch: Patch) -> tuple[np.ndarray, np.ndarray]:
    """Hauteur et normale du sol aux 81 points de la grille 9 × 9 du sous-carreau (maillage
    adaptatif : les points absents sont lus sur les triangles fins), indexées par `g = 9·i + j`."""
    z = np.full(81, np.nan)
    n = np.zeros((81, 3))
    local = patch.points[:, :2] - np.array([8 * patch.sx, 8 * patch.sy])
    g = np.round(local[:, 0]).astype(int) * 9 + np.round(local[:, 1]).astype(int)
    z[g] = patch.points[:, 2]
    n[g] = patch.normals
    missing = np.where(np.isnan(z))[0]
    for q in missing:
        px, py = q // 9, q % 9
        for tri in patch.triangles:
            a, b, c = local[tri]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            w0 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
            w1 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
            w2 = 1 - w0 - w1
            if min(w0, w1, w2) >= -1e-6:
                w = np.array([w0, w1, w2])
                z[q] = w @ patch.points[tri, 2]
                nn = w @ patch.normals[tri]
                n[q] = nn / max(np.linalg.norm(nn), 1e-9)
                break
    z[np.isnan(z)] = np.nanmean(z) if np.isfinite(z).any() else 0.0
    return z, n


def region_patches(get, map_name: str, region_path: str) -> tuple[list[tuple[int, ...]], list[Patch]] | None:
    """Terrain d'une région (`Maps/X/000_000/5_4_MapRegion.xdb` → `…/5_4_terrainDump.bin`)."""
    chunk = _dump_chunk(get, region_path)
    if not chunk or len(chunk) < 0x40:
        return None
    return parse_terrain_dump(chunk)


def region_extras(get, region_path: str) -> TerrainExtras | None:
    """Occulteurs, herbe et eau du `terrainDump` d'une région."""
    chunk = _dump_chunk(get, region_path)
    return parse_terrain_extras(chunk) if chunk else None


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


def region_splats(get, region_path: str) -> list[np.ndarray | None]:
    """Poids des `SplatMap_0…2` de la région (`None` pour un atlas absent), indexés par le numéro
    que porte le jeu de calques d'une passe."""
    from tools.extract_menu_scene import read_chunks
    out: list[np.ndarray | None] = []
    for k in range(SPLAT_MAPS):
        raw = get(region_path.replace("_MapRegion.xdb", f"_SplatMap_{k}.(Texture).bin"))
        chunk = read_chunks(raw).get(0) if raw else None
        out.append(splat_weights(chunk) if chunk and len(chunk) >= 256 * 256 * 2 else None)
    return out
