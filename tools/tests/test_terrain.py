"""Tests du lecteur de terrain `terrainDump` (données synthétiques)."""
import struct

import numpy as np

from tools.allods_terrain import parse_terrain_dump, splat_weights


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
    raw[sets_at:sets_at + 9] = bytes([0, 1, 0, 0, 0x0B, 0x0D, 0xFF, 0, 0])
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
    assert patch.triangles.tolist() == [[0, 2, 1]] and patch.passes == [(0, 0)]
    assert np.allclose(patch.normals[0], [0, 0, 1], atol=0.01)


def test_splat_weights_decode_r5g6b5():
    raw = np.full(256 * 256, 0xF800, "<u2").tobytes()
    w = splat_weights(raw)
    assert w.shape == (256, 256, 3) and np.allclose(w[0, 0], [1, 0, 0])
