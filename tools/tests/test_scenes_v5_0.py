"""Crochets 5.0 (`tools/scenes/v5_0.py`) et décodage des pistes à drapeaux (échelle, angles d'Euler)."""
from __future__ import annotations

import math
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from tools.extract_menu_scene import (
    GltfBuilder,
    JointTrack,
    Skeleton,
    SkeletalAnimation,
    _emit_skeleton,
    _read_track_flags,
    parse_skeletal_animation,
    rest_world_matrices,
)
from tools.scenes import hooks_for
from tools.scenes.v5_0 import material, positions

IDENTITY = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


def _skeleton(names, parents, translations, inverse_translations=None):
    n = len(names)
    local = np.zeros((n, 4, 3))
    inverse = np.zeros((n, 4, 3))
    for i in range(n):
        local[i, :3] = IDENTITY
        local[i, 3] = translations[i]
        inverse[i, :3] = IDENTITY
        if inverse_translations is not None:
            inverse[i, 3] = inverse_translations[i]
    return Skeleton(names=list(names), parents=list(parents), local=local, inverse=inverse, order=list(range(n)))


# --- crochets ----------------------------------------------------------------------------------

def test_hooks_are_registered_for_5_0():
    hooks = hooks_for("5.0")
    assert hooks.material is material and hooks.positions is positions
    assert hooks.extra_roots is None and hooks.after_export is None


def test_material_additive_only_when_transparent():
    assert material(SimpleNamespace(transparent=True), True) is True
    assert material(SimpleNamespace(transparent=False), True) is False   # écorces, bielles
    assert material(SimpleNamespace(transparent=True), False) is False


def test_positions_bake_native_frame_of_identity_inverse_joints():
    """Inverse de bind identité (le navire, la tour) : les sommets sont dans le repère de
    l'articulation, ils reçoivent sa pose de repos. Inverse « vraie » : ils ne bougent pas."""
    skeleton = _skeleton(["Root", "Wheel"], [0xFFFF, 0], [(0.0, 0.0, 0.0), (10.0, 0.0, 5.0)])
    vertices = {
        "position": np.array([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]], np.float32),
        "indices": np.array([[3, 255, 255, 255], [0, 255, 255, 255]], np.uint8),   # palette : 3 = joint 1
        "weights": np.array([[255, 0, 0, 0], [255, 0, 0, 0]], np.uint8),
    }
    obj = SimpleNamespace(skeleton=skeleton, vertices=vertices, animation=None)
    out = positions("Any", obj, vertices["position"])
    assert out.dtype == np.float32
    assert out[0].tolist() == pytest.approx([11.0, 0.0, 5.0])   # joint 1 : + (10, 0, 5)
    assert out[1].tolist() == pytest.approx([0.0, 2.0, 0.0])    # racine à l'origine

    # Une inverse native qui annule la pose (sommets déjà en espace monde) laisse tout en place.
    world_space = _skeleton(["Root", "Wheel"], [0xFFFF, 0], [(0.0, 0.0, 0.0), (10.0, 0.0, 5.0)],
                            inverse_translations=[(0.0, 0.0, 0.0), (-10.0, 0.0, -5.0)])
    obj = SimpleNamespace(skeleton=world_space, vertices=vertices, animation=None)
    assert np.allclose(positions("Any", obj, vertices["position"]), vertices["position"])


def test_positions_leave_unskinned_objects_alone():
    obj = SimpleNamespace(skeleton=None, vertices={"position": np.zeros((2, 3), np.float32)}, animation=None)
    out = positions("Any", obj, obj.vertices["position"])
    assert out is obj.vertices["position"]


# --- pistes à drapeaux ------------------------------------------------------------------------

def _pointer(target: int, field: int) -> int:
    return target - field


def build_flagged_animation(frames: int, nodes: list[dict]) -> bytes:
    """Blob d'animation au format du jeu : entête de 44 octets, table de descripteurs
    (20 o/nœud), table des noms, corps (flottants puis courbes), table d'ordre.

    Chaque nœud : `{name, flags, floats: [...], curves: [[...] par canal animé]}` ; les
    courbes sont écrites entrelacées par image, en `u16` (une valeur négative est relue en `i16`).
    """
    n = len(nodes)
    p_desc = 44
    p_names = p_desc + 20 * n
    p_bodies = p_names + 8 * n
    bodies = bytearray()
    layout = []
    for node in nodes:
        name = node["name"].encode("ascii") + b"\0"
        addr = p_bodies + len(bodies)
        bodies += name + b"\0" * ((4 - len(name) % 4) % 4)
        floats_at = p_bodies + len(bodies)
        bodies += struct.pack(f"<{len(node['floats'])}f", *node["floats"])
        curves = node.get("curves") or []
        curves_at = p_bodies + len(bodies)
        for frame in range(frames):
            bodies += struct.pack(f"<{len(curves)}H", *(int(c[frame]) & 0xFFFF for c in curves))
        bodies += b"\0" * ((4 - len(bodies) % 4) % 4)
        layout.append((addr, len(name), floats_at, curves_at, len(curves)))
    p_order = p_bodies + len(bodies)
    buf = bytearray(p_bodies) + bodies + bytearray(2 * n)
    struct.pack_into("<HHI", buf, 0, 30, frames, _pointer(p_desc, 4))
    struct.pack_into("<II", buf, 8, n, _pointer(p_names, 12))
    struct.pack_into("<II", buf, 16, n, _pointer(p_order, 20))
    struct.pack_into("<II", buf, 24, n, _pointer(p_desc, 28))
    for i, node in enumerate(nodes):
        addr, name_len, floats_at, curves_at, channels = layout[i]
        field = p_desc + 20 * i
        struct.pack_into("<HHIIII", buf, field, node["flags"], channels,
                         _pointer(curves_at, field + 4), frames * channels,
                         _pointer(floats_at, field + 12), len(node["floats"]))
        struct.pack_into("<II", buf, p_names + 8 * i, _pointer(addr, p_names + 8 * i), name_len)
        struct.pack_into("<H", buf, p_order + 2 * i, i)
    return bytes(buf)


def test_read_track_flags_reads_descriptor_table_and_rejects_inconsistent_one():
    blob = build_flagged_animation(4, [{"name": "Gear", "flags": 0x3B,
                                        "floats": [1.0, 2.0, -1.0, 0.001, 1.16, 0.0, 0.0],
                                        "curves": [[0, 100, 200, 300], [0, 8192, 16384, 24576]]}])
    assert _read_track_flags(blob, 1, 4) == [0x3B]
    assert _read_track_flags(blob, 1, 5) is None   # nb_valeurs ≠ images × canaux


def test_gear_track_rotates_around_x_at_fixed_scale():
    """Drapeau 0x3B : Tz et le troisième angle (X) animés, échelle fixe 1,16."""
    frames = 4
    blob = build_flagged_animation(frames, [{"name": "Gear", "flags": 0x3B,
                                             "floats": [-51.0, 24.5, -12.0, 0.001, 1.16, 0.0, 0.0],
                                             "curves": [[0, 1000, 2000, 3000], [0, 8192, 16384, -16384]]}])
    animation = parse_skeletal_animation(blob)
    assert animation.undecoded == []
    track = animation.tracks[0]
    assert track.animated is True
    assert track.translation[:, 0].tolist() == [-51.0] * frames
    assert track.translation[2][2] == pytest.approx(-12.0 + 2000 * 0.001)
    assert track.scale.tolist() == pytest.approx([1.16] * frames)
    # 8192 / 32767 tour ≈ 90° autour de X : quaternion (sin 45°, 0, 0, cos 45°)
    angle = 8192 / 32767 * 2 * math.pi
    assert track.rotation[1].tolist() == pytest.approx([math.sin(angle / 2), 0.0, 0.0, math.cos(angle / 2)], abs=1e-6)
    assert track.rotation[2][0] == pytest.approx(math.sin(16384 / 32767 * math.pi), abs=1e-6)  # ≈ 180°
    assert np.linalg.norm(track.rotation, axis=1).tolist() == pytest.approx([1.0] * frames)


def test_ship_track_animates_scale_and_composes_euler_zyx():
    """Drapeau 0 : tout animé — 8 flottants (4 couples base/échelle), 7 canaux."""
    frames = 3
    blob = build_flagged_animation(frames, [{"name": "Ship", "flags": 0x00,
                                             "floats": [-36.0, 0.002, -165.0, 0.004, 5.4, 0.001, -0.0013, 0.00001],
                                             "curves": [[0, 1, 2], [0, 0, 0], [0, 0, 0], [0, 32768, -1],
                                                        [8192, 0, 0], [0, 8192, 0], [0, 0, 8192]]}])
    track = parse_skeletal_animation(blob).tracks[0]
    assert track.translation[1][0] == pytest.approx(-36.0 + 0.002)
    assert track.scale[0] == pytest.approx(-0.0013)              # naît à l'échelle ~0
    assert track.scale[1] == pytest.approx(-0.0013 + 32768 * 0.00001)
    assert track.scale[2] == pytest.approx(-0.0013 + 65535 * 0.00001)   # -1 relu en u16
    half = 8192 / 32767 * math.pi
    # emplacement 0 → Z, 1 → Y, 2 → X
    assert track.rotation[0].tolist() == pytest.approx([0.0, 0.0, math.sin(half), math.cos(half)], abs=1e-6)
    assert track.rotation[1].tolist() == pytest.approx([0.0, math.sin(half), 0.0, math.cos(half)], abs=1e-6)
    assert track.rotation[2].tolist() == pytest.approx([math.sin(half), 0.0, 0.0, math.cos(half)], abs=1e-6)


def test_rest_pose_includes_scale_and_stays_invertible():
    skeleton = _skeleton(["Root"], [0xFFFF], [(1.0, 2.0, 3.0)])
    grown = SkeletalAnimation(fps=30, frames=2, tracks=[JointTrack(
        "Root", np.array([[1.0, 2.0, 3.0]] * 2), np.array([[0.0, 0.0, 0.0, 1.0]] * 2), True, np.array([2.0, 3.0]))])
    world = rest_world_matrices(skeleton, grown)
    assert np.allclose(world[0][:3, :3], 2.0 * np.eye(3)) and world[0][:3, 3].tolist() == [1.0, 2.0, 3.0]
    born = SkeletalAnimation(fps=30, frames=2, tracks=[JointTrack(
        "Root", np.array([[0.0, 0.0, 0.0]] * 2), np.array([[0.0, 0.0, 0.0, 1.0]] * 2), True, np.array([0.0, 1.0]))])
    world = rest_world_matrices(skeleton, born)
    assert abs(np.linalg.det(world[0])) > 0  # échelle 0 bornée à 1e-3
    assert world[0][0, 0] == pytest.approx(1e-3)


def test_emit_skeleton_writes_a_scale_channel_when_the_scale_moves():
    skeleton = _skeleton(["Root"], [0xFFFF], [(0.0, 0.0, 0.0)])
    animation = SkeletalAnimation(fps=30, frames=3, tracks=[JointTrack(
        "Root", np.zeros((3, 3)), np.array([[0.0, 0.0, 0.0, 1.0]] * 3), True, np.array([0.5, 1.0, 1.5]))])
    gltf = GltfBuilder()
    names: list[str] = []
    nodes = _emit_skeleton(gltf, skeleton, animation, "Obj", names)
    assert gltf.json["nodes"][nodes[0]]["scale"] == [0.5, 0.5, 0.5]
    paths = [c["target"]["path"] for c in gltf.json["animations"][0]["channels"]]
    assert paths == ["translation", "rotation", "scale"]
    assert names == ["Obj"]
