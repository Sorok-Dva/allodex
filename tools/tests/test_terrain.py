"""Tests du lecteur de terrain `terrainDump` (données synthétiques)."""
import struct

import numpy as np

from tools.allods_terrain import LAYER_REPEAT, layer_uv, parse_terrain_dump, splat_weights


def _dump() -> bytes:
    """Un jeu de calques (11, 13), un carreau, un sous-carreau (2, 3) de 3 sommets, 1 triangle."""
    header_size = 0x38
    sets_at = header_size
    tiles_at = sets_at + 9
    sub_at = tiles_at + 32
    coarse_at = sub_at + 40
    fine_at = coarse_at + 3
    passes_at = fine_at + 3
    verts_at = passes_at + 6
    end = verts_at + 3 * 8
    raw = bytearray(end)

    def selfptr(field: int, target: int, count: int) -> None:
        struct.pack_into("<II", raw, field, target - field, count)
    selfptr(0x08, sets_at, 1)
    selfptr(0x10, tiles_at, 1)
    raw[sets_at:sets_at + 9] = bytes([0, 1, 0, 0, 0x0B, 0x0D, 0xFF, 0, 1])   # SplatMap_1
    struct.pack_into("<6f", raw, tiles_at, 16, 16, 0, 16, 16, 1)
    selfptr(tiles_at + 24, sub_at, 1)
    selfptr(sub_at + 0, coarse_at, 3)
    selfptr(sub_at + 8, fine_at, 3)
    selfptr(sub_at + 16, verts_at, 24)
    selfptr(sub_at + 24, passes_at, 1)
    struct.pack_into("<II", raw, sub_at + 32, 2 | (3 << 16), 3 | (1 << 16))
    raw[coarse_at:coarse_at + 3] = bytes([0, 1, 2])
    raw[fine_at:fine_at + 3] = bytes([0, 2, 1])
    struct.pack_into("<HHBB", raw, passes_at, 0, 0, 0, 0)
    for k, g in enumerate((0, 8, 80)):                 # coins (0,0), (0,8), (8,8) de la grille 9 × 9
        raw[verts_at + 4 * k:verts_at + 4 * k + 4] = bytes([128, 128, 255, g])
    struct.pack_into("<3f", raw, verts_at + 12, 1.0, 2.0, 3.0)
    return bytes(raw)


def test_parse_terrain_dump_places_grid_vertices_with_float_heights():
    sets, patches = parse_terrain_dump(_dump())
    assert sets == [(11, 13)]
    (patch,) = patches
    assert (patch.sx, patch.sy, patch.level) == (2, 3, 1)
    assert patch.points.tolist() == [[16, 24, 1], [16, 32, 2], [24, 32, 3]]
    assert patch.triangles.tolist() == [[0, 2, 1]] and patch.passes == [(0, 0, 0, 0, 1)]
    assert np.allclose(patch.normals[0], [0, 0, 1], atol=0.01)


def test_splat_weights_decode_r5g6b5():
    raw = np.full(256 * 256, 0xF800, "<u2").tobytes()
    w = splat_weights(raw)
    assert w.shape == (256, 256, 3) and np.allclose(w[0, 0], [1, 0, 0])


def test_pass_weights_read_the_8x8_block_with_shared_edges():
    from tools.allods_terrain import Patch, pass_weights
    splat = np.zeros((256, 256, 3))
    splat[8:16, 16:24, 0] = np.linspace(0, 1, 8)[:, None]      # bloc (c=1, d=2) : R croît avec la ligne
    splat[8:16, 16:24, 1] = 1 - splat[8:16, 16:24, 0]
    patch = Patch(3, 5, np.array([[24.0, 40.0, 0.0], [32.0, 40.0, 0.0], [28.0, 44.0, 0.0]]), np.zeros((3, 3)),
                  np.zeros((0, 3), int), np.zeros((0, 3), int), [])
    w = pass_weights(splat, patch, (1, 2))
    assert np.allclose(w[:, 0], [0.0, 1.0, 0.5]) and np.allclose(w.sum(1), 1.0)
    assert np.allclose(pass_weights(None, patch, (0, 0)), [[1, 0, 0]] * 3)


def _extras_dump() -> bytes:
    """Entête de 7 vecteurs : 1 tampon complexe, 1 occulteur, 1 carreau d'herbe (2 jeux), 1 matériau
    d'eau, 1 carreau d'eau de 2 éléments."""
    buf_at, occ_at, grass_at = 0x38, 0x3C, 0x3C + 56
    sets_at = grass_at + 36
    xy0_at = sets_at + 24
    xy1_at = xy0_at + 4
    mat_at = xy1_at + 4
    water_at = mat_at + 4
    elem_at = water_at + 84
    raw = bytearray(elem_at + 8)

    def selfptr(field: int, target: int, count: int) -> None:
        struct.pack_into("<II", raw, field, target - field, count)
    selfptr(0x00, buf_at, 1)
    struct.pack_into("<HBB", raw, buf_at, 300, 1, 0)
    selfptr(0x18, occ_at, 1)
    struct.pack_into("<14f", raw, occ_at, 1, 2, 3, 4, *([-3.4e38] * 4), 16, 48, 0, 16, 16, 512)
    selfptr(0x20, grass_at, 1)
    struct.pack_into("<6f", raw, grass_at, 16, 48, 0, 17, 17, 1)
    selfptr(grass_at + 24, sets_at, 2)
    struct.pack_into("<HH", raw, grass_at + 32, 0, 1)
    raw[sets_at:sets_at + 2] = bytes([21, 2])
    selfptr(sets_at + 4, xy0_at, 2)
    raw[sets_at + 12:sets_at + 14] = bytes([21, 0x82])
    selfptr(sets_at + 16, xy1_at, 2)
    raw[xy0_at:xy0_at + 4] = bytes([3, 5, 31, 0])
    raw[xy1_at:xy1_at + 4] = bytes([3, 5, 31, 0])
    selfptr(0x28, mat_at, 1)
    struct.pack_into("<BBH", raw, mat_at, 0, 1, 8)
    selfptr(0x30, water_at, 1)
    struct.pack_into("<18f", raw, water_at, 184, 48, -44, 8, 16, 0, *([-44.5] * 4), *([0.0] * 8))
    selfptr(water_at + 72, elem_at, 2)
    raw[water_at + 80:water_at + 84] = bytes([160, 32, 0, 1])
    raw[elem_at:elem_at + 8] = bytes([25, 13, 16, 0, 25, 14, 16, 8])
    return bytes(raw)


def test_parse_terrain_extras_reads_occluders_grass_and_water():
    from tools.allods_terrain import parse_terrain_extras
    ex = parse_terrain_extras(_extras_dump())
    assert ex.buffers == [(300, True)]
    (occ,) = ex.occluders
    assert occ.xmin == (1, 2, 3, 4) and occ.center == (16, 48, 0) and occ.extents == (16, 16, 512)
    (cell,) = ex.grass
    assert (cell.i, cell.j) == (0, 1)
    assert [(s.layer, s.foliage, s.flag) for s in cell.sets] == [(21, 2, False), (21, 2, True)]
    assert cell.sets[0].xy.tolist() == [[3, 5], [31, 0]]
    assert ex.water_materials == [(False, 1, 8)]
    (water,) = ex.water
    assert (water.ox, water.oy, water.material, water.water) == (160, 32, 0, 1)
    assert water.height == (-44.5,) * 4 and water.elements.tolist() == [[25, 13, 16, 0], [25, 14, 16, 8]]


def test_parse_terrain_extras_of_a_dump_without_them_is_empty():
    from tools.allods_terrain import parse_terrain_extras
    ex = parse_terrain_extras(_dump())
    assert not ex.occluders and not ex.grass and not ex.water and not ex.buffers


def test_grid_samples_fill_the_points_the_adaptive_mesh_leaves_out():
    from tools.allods_terrain import Patch, grid_samples
    # Deux triangles couvrant le sous-carreau (1, 2), sommets aux quatre coins seulement.
    pts = np.array([[8, 16, 0.0], [16, 16, 8.0], [8, 24, 0.0], [16, 24, 8.0]])
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    patch = Patch(1, 2, pts, normals, np.array([[0, 1, 2], [2, 1, 3]]), np.zeros((0, 3), int), [])
    z, n = grid_samples(patch)
    assert z[0] == 0 and z[80] == 8 and np.isclose(z[9 * 4 + 4], 4.0) and np.isclose(z[9 * 2 + 7], 2.0)
    assert np.allclose(n[40], [0, 0, 1])


class _FakeDB:
    """Mémoire à plat : `ptr` et `vec` décrits par des tables, nombres lus dans un tampon."""

    def __init__(self, size: int):
        self.raw = bytearray(size)
        self.ptrs: dict[int, int] = {}
        self.vecs: dict[int, tuple[int, int]] = {}
        self.types: dict[int, str] = {}

    def ptr(self, off):
        return self.ptrs.get(off)

    def vec(self, off):
        return self.vecs.get(off)

    def vtype(self, off):
        return self.types.get(off)

    def i32(self, off):
        return struct.unpack_from("<i", self.raw, off)[0]

    def u32(self, off):
        return struct.unpack_from("<I", self.raw, off)[0]

    def f32(self, off):
        return struct.unpack_from("<f", self.raw, off)[0]

    def floats(self, off, n):
        return struct.unpack_from(f"<{n}f", self.raw, off)

    def string(self, off):
        v = self.vec(off)
        return None if v is None else bytes(self.raw[v[0]:v[0] + v[1]]).decode()

    def binary_ref(self, off):
        return (0, off)

    def elements(self, off, stride):
        v = self.vec(off)
        return [] if v is None else [v[0] + stride * k for k in range(v[1] // stride)]


class _FakeCat:
    def __init__(self, names):
        self.names = names

    def name(self, ref):
        return self.names.get(ref[1])


def test_terrain_foliage_and_water_layers_read_the_17_0_layouts():
    from tools.allods_terrain import (FOLIAGE_STRIDE, LAYER_FOLIAGE, LAYER_STRIDE, WATER_LAYER_STRIDE, foliage_atlas,
                                      terrain_foliage, water_layers)
    db = _FakeDB(4096)
    terra, layers, water, atlas, sources = 0, 256, 1024, 2048, 2200
    db.vecs[terra + 0x30] = (layers, LAYER_STRIDE)
    f = layers + LAYER_FOLIAGE + FOLIAGE_STRIDE * 1           # foliage1 de ZC10_Grass_04 (7.0)
    struct.pack_into("<3f", db.raw, f, 0.0, 0.0, 0.3)
    struct.pack_into("<ffii", db.raw, f + 0x18, 1.0, 1.35, 3, 30)
    struct.pack_into("<3f", db.raw, f + 0x34, 0.55, 0.15, 0.4)
    db.ptrs[f + 0x28] = 3000
    (row,) = terrain_foliage(db, terra)
    assert row[1].element == 3000 and (row[1].probability, row[1].leaves) == (30, 3)
    assert (round(row[1].min_scale, 2), row[1].max_scale) == (1.35, 1.0) and row[1].top == (0.55, 0.15, 0.4)
    assert row[1].bottom == (0.0, 0.0, 0.3) and row[0].element is None
    db.ptrs[terra + 0x60] = atlas
    db.types[atlas] = "TextureAtlas"
    db.ptrs[atlas + 0x28] = 3100
    db.types[3100] = "Texture"
    db.vecs[atlas + 0x30] = (sources, 48)
    struct.pack_into("<ii", db.raw, sources, 0, 256)
    db.ptrs[sources + 8] = 3000
    struct.pack_into("<ii", db.raw, sources + 0x10, 256, 0)
    struct.pack_into("<i", db.raw, sources + 0x20, 768)
    cat = _FakeCat({3100: "Maps/Ferris4/layers.(Texture).bin", 3200: "World/Generic/Water/Textures/WaterNoise.(Texture).bin"})
    assert foliage_atlas(db, cat, terra) == ("Maps/Ferris4/layers.(Texture).bin", {3000: (0, 768, 256, 256)})
    db.vecs[terra + 0x90] = (water, WATER_LAYER_STRIDE)
    db.raw[3500:3511] = b"Kania_River"
    db.vecs[water + 0x08] = (3500, 11)
    db.ptrs[water + 0x20] = 3200
    db.types[3200] = "Texture"
    struct.pack_into("<fffi", db.raw, water + 0x48, 1.0, 1.0, 0.0, 16)
    (w,) = water_layers(db, cat, terra)
    assert w["name"] == "Kania_River" and w["textures"]["bump"].endswith("WaterNoise.(Texture).bin")
    assert (w["alpha"], w["reflection"], w["specular"], w["speed"]) == (1.0, 1.0, 0.0, 16)
    assert w["textures"]["fresnelDown"] is None


def test_layer_uv_follows_the_terrain_shader_one_repeat_per_8_m():
    """`terrain-dx11` : `TEXCOORD0 = −position · 0,125`, pour tous les calques."""
    assert LAYER_REPEAT == 8.0
    uv = layer_uv(np.array([[0.0, 0.0], [8.0, 4.0], [256.0, -16.0]]))
    assert uv.dtype == np.float32
    assert np.allclose(uv, [[0, 0], [-1, -0.5], [-32, 2]])
