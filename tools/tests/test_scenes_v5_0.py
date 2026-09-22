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
    assert hooks.extra_roots is None and hooks.after_export is not None


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


# --- angles fixes de la pose de bind ---------------------------------------------------------

def _rotation_skeleton(names, parents, rows_list, translations):
    n = len(names)
    local = np.zeros((n, 4, 3))
    inverse = np.zeros((n, 4, 3))
    for i in range(n):
        local[i, :3] = rows_list[i]
        local[i, 3] = translations[i]
        inverse[i, :3] = IDENTITY
    return Skeleton(names=list(names), parents=list(parents), local=local, inverse=inverse, order=list(range(n)))


def _euler_track(name, az, ay, ax, frames=3):
    from tools.extract_menu_scene import _euler_zyx_quaternion
    q = _euler_zyx_quaternion(np.full(frames, az), np.full(frames, ay), np.full(frames, ax))
    return JointTrack(name, np.zeros((frames, 3)), q, True, np.ones(frames))


def _rows_of(az, ay, ax):
    """Matrice locale 3×4 du squelette (lignes = base) pour R = Rz·Ry·Rx."""
    from tools.extract_menu_scene import _euler_zyx_quaternion, quat_matrix
    R = quat_matrix(_euler_zyx_quaternion(np.array([az]), np.array([ay]), np.array([ax]))[0])
    return R.T  # colonnes de R = lignes stockées


def test_euler_zyx_round_trip_including_gimbal_lock():
    from tools.extract_menu_scene import _euler_zyx_quaternion, quat_matrix
    from tools.scenes.v5_0 import euler_zyx
    for angles in [(0.3, -1.1, 2.5), (math.pi, math.radians(98.4), 0.0), (0.7, math.pi / 2, -0.4)]:
        R = quat_matrix(_euler_zyx_quaternion(*[np.array([a]) for a in angles])[0])
        back = quat_matrix(_euler_zyx_quaternion(*[np.array([a]) for a in euler_zyx(R)])[0])
        assert np.allclose(R, back, atol=1e-6)


def test_restore_fixed_rotations_uses_bind_for_fully_fixed_and_picks_the_matching_branch():
    from tools.extract_menu_scene import quat_matrix
    from tools.scenes.v5_0 import restore_fixed_rotations
    z180, y98 = math.pi, math.radians(98.4)
    skeleton = _rotation_skeleton(
        ["root", "piston", "leaf", "free"], [0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF],
        [_rows_of(0.4, -0.2, 3.0),      # rotation fixe non écrite dans l'animation
         _rows_of(z180, y98, 0.0),      # Y animé, Z fixe à 180° : la branche (0°, 81.6°, 180°) est la mauvaise
         _rows_of(0.0, 0.0, 0.0),       # bind identité : rien à faire
         _rows_of(1.0, 0.5, 0.2)],      # tout animé : intouché
        [(0, 0, 0)] * 4)
    animation = SkeletalAnimation(fps=30, frames=3, tracks=[
        _euler_track("root", 0.0, 0.0, 0.0),
        _euler_track("piston", 0.0, y98, 0.0),
        _euler_track("leaf", 0.0, 0.0, 0.0),
        _euler_track("free", 0.9, 0.4, 0.1),
    ])
    obj = SimpleNamespace(skeleton=skeleton, animation=animation)
    assert restore_fixed_rotations(obj) == ["root", "piston"]
    assert np.allclose(quat_matrix(animation.tracks[0].rotation[0]), skeleton.local[0][:3].T, atol=1e-6)
    assert np.allclose(quat_matrix(animation.tracks[1].rotation[2]), skeleton.local[1][:3].T, atol=1e-6)
    assert np.allclose(quat_matrix(animation.tracks[2].rotation[0]), np.eye(3), atol=1e-6)
    free = quat_matrix(animation.tracks[3].rotation[0])
    assert not np.allclose(free, skeleton.local[3][:3].T, atol=1e-3)
    assert restore_fixed_rotations(obj) == []   # idempotent


def test_restore_fixed_rotations_leaves_a_track_that_already_reaches_the_bind():
    """`ship_tail` : bind identité, Z animé à 180° tant que l'échelle est nulle puis 0 ensuite.

    La pose de bind n'est pas celle de l'image 0 : la piste brute l'atteint plus tard, donc les
    canaux fixes laissés à 0 sont les bons. Sans ce garde, la branche choisie sur l'image 0
    posait 180° sur Y et X et retournait la traînée d'un demi-tour autour de Z — la bulle
    autour du navire de raid.
    """
    from tools.extract_menu_scene import _euler_zyx_quaternion, quat_matrix
    from tools.scenes.v5_0 import restore_fixed_rotations
    skeleton = _rotation_skeleton(["ship_tail"], [0xFFFF], [_rows_of(0.0, 0.0, 0.0)], [(0, 0, 0)])
    az = np.array([math.pi, math.pi, 0.0, 0.0])
    zeros = np.zeros(4)
    track = JointTrack("ship_tail", np.zeros((4, 3)), _euler_zyx_quaternion(az, zeros, zeros),
                       True, np.array([0.0, 0.0, 1.0, 1.0]))
    before = track.rotation.copy()
    obj = SimpleNamespace(skeleton=skeleton, animation=SkeletalAnimation(fps=30, frames=4, tracks=[track]))
    assert restore_fixed_rotations(obj) == []
    assert np.allclose(track.rotation, before)
    # les images où l'élément est visible gardent bien l'identité
    assert np.allclose(quat_matrix(track.rotation[2]), np.eye(3), atol=1e-6)


def test_restore_fixed_rotations_still_fires_when_the_track_never_reaches_the_bind():
    """Une bielle : Y animé autour de la valeur du bind, Z fixe à 180° jamais écrit.

    Sa piste brute (Z = X = 0) ne porte à aucune image la rotation de bind : le garde ne
    s'applique pas et la substitution a bien lieu.
    """
    from tools.extract_menu_scene import _euler_zyx_quaternion, quat_matrix
    from tools.scenes.v5_0 import reaches_bind, restore_fixed_rotations
    y98 = math.radians(98.4)
    skeleton = _rotation_skeleton(["piston"], [0xFFFF], [_rows_of(math.pi, y98, 0.0)], [(0, 0, 0)])
    ay = np.array([y98, 0.5, 1.0])
    track = JointTrack("piston", np.zeros((3, 3)), _euler_zyx_quaternion(np.zeros(3), ay, np.zeros(3)),
                       True, np.ones(3))
    assert not reaches_bind(track.rotation, math.pi, y98, 0.0)
    obj = SimpleNamespace(skeleton=skeleton, animation=SkeletalAnimation(fps=30, frames=3, tracks=[track]))
    assert restore_fixed_rotations(obj) == ["piston"]
    assert np.allclose(quat_matrix(track.rotation[0]), skeleton.local[0][:3].T, atol=1e-6)


def test_reaches_bind_compares_rotations_not_quaternion_signs():
    from tools.extract_menu_scene import _euler_zyx_quaternion
    from tools.scenes.v5_0 import reaches_bind
    q = _euler_zyx_quaternion(np.array([0.4, 1.2]), np.array([-0.2, 0.0]), np.array([3.0, 0.5]))
    assert reaches_bind(-q, 0.4, -0.2, 3.0)          # -q et q décrivent la même rotation
    assert not reaches_bind(q, 0.9, 0.4, 0.1)


def test_restore_fixed_rotations_keeps_a_fixed_axis_at_ninety_degrees():
    """`joint9` : Y fixe à 90° (blocage de cardan), Z et X animés ; le décodeur lit Y = 0."""
    from tools.extract_menu_scene import quat_matrix
    from tools.scenes.v5_0 import restore_fixed_rotations
    z, x = math.radians(45.0), math.radians(64.2)
    skeleton = _rotation_skeleton(["joint9"], [0xFFFF], [_rows_of(z, math.pi / 2, x)], [(0, 0, 0)])
    animation = SkeletalAnimation(fps=30, frames=2, tracks=[_euler_track("joint9", z, 0.0, x, frames=2)])
    obj = SimpleNamespace(skeleton=skeleton, animation=animation)
    assert restore_fixed_rotations(obj) == ["joint9"]
    assert np.allclose(quat_matrix(animation.tracks[0].rotation[1]), skeleton.local[0][:3].T, atol=1e-6)


def test_positions_leave_painted_elements_in_world_space():
    """`skinIndex -1` : le tampon lie ces sommets à l'articulation 0, le client ne les skinne pas."""
    skeleton = _skeleton(["Rock", "Static"], [0xFFFF, 0xFFFF], [(10.0, 0.0, 5.0), (0.0, 0.0, 0.0)])
    vertices = {
        "position": np.array([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [3.0, 3.0, 3.0]], np.float32),
        "indices": np.array([[0, 255, 255, 255]] * 3, np.uint8),
        "weights": np.array([[255, 0, 0, 0]] * 3, np.uint8),
    }
    painted = SimpleNamespace(name="Back6", ib0=3, ib1=6, skin_index=-1)
    skinned = SimpleNamespace(name="Rock", ib0=0, ib1=3, skin_index=0)
    doc = SimpleNamespace(elements=[skinned, painted])
    obj = SimpleNamespace(skeleton=skeleton, vertices=vertices, animation=None, doc=doc,
                          indices=np.array([0, 0, 0, 1, 2, 2], np.uint32))
    out = positions("Any", obj, vertices["position"])
    assert out[0].tolist() == pytest.approx([11.0, 0.0, 5.0])   # skinné : repère natif cuit
    assert out[1].tolist() == pytest.approx([0.0, 2.0, 0.0])    # peint : intact
    assert out[2].tolist() == pytest.approx([3.0, 3.0, 3.0])


# --- méta : ordre de peinture et drapeaux de matériau ---------------------------------------

XDB = """<Geometry>
  <sortMode>OFFSETS</sortMode>
  <modelElements>
    <Item><name>Back6</name><lods><Item><indexBufferBegin>0</indexBufferBegin><indexBufferEnd>6</indexBufferEnd></Item></lods>
      <material><BlendEffect>BLEND_EFFECT_ALPHA</BlendEffect><transparent>false</transparent><visible>true</visible></material></Item>
    <Item><name>Hidden</name><lods><Item><indexBufferBegin>6</indexBufferBegin><indexBufferEnd>9</indexBufferEnd></Item></lods>
      <material><BlendEffect>BLEND_EFFECT_ALPHA</BlendEffect><transparent>true</transparent><visible>false</visible></material></Item>
    <Item><name>Empty</name><lods><Item><indexBufferBegin>9</indexBufferBegin><indexBufferEnd>9</indexBufferEnd></Item></lods>
      <material><BlendEffect>BLEND_EFFECT_ALPHA</BlendEffect><transparent>true</transparent></material></Item>
    <Item><name>Glow_L</name><lods><Item><indexBufferBegin>9</indexBufferBegin><indexBufferEnd>12</indexBufferEnd></Item></lods>
      <material><BlendEffect>BLEND_EFFECT_ADD</BlendEffect><transparent>true</transparent></material></Item>
  </modelElements>
</Geometry>"""


def test_read_materials_follows_the_exporter_primitive_order():
    from tools.scenes.v5_0 import read_materials
    assert read_materials(XDB) == [
        {"element": "Back6", "blend": "alpha", "transparent": False},
        {"element": "Glow_L", "blend": "add", "transparent": True},
    ]


def test_after_export_records_sort_mode_and_materials(tmp_path):
    from tools.scenes.v5_0 import after_export
    directory = tmp_path / "World" / "MainMenu" / "Animated_Background_5_0"
    directory.mkdir(parents=True)
    (directory / "Animated_Background_5_0.(Geometry).xdb").write_text(XDB, encoding="utf-8")
    (directory / "Raid_Ship.(Geometry).xdb").write_text(XDB.replace("Back6", "Ship"), encoding="utf-8")
    meta = {"version": "5.0"}
    after_export(tmp_path / "out", meta, None, tmp_path)
    assert meta["sortMode"] == "OFFSETS"
    assert [m["element"] for m in meta["materials"]["Animated_Background_5_0"]] == ["Back6", "Glow_L"]
    assert meta["materials"]["Raid_Ship"][0] == {"element": "Ship", "blend": "alpha", "transparent": False}
    untouched = {"version": "5.0"}
    after_export(tmp_path / "out", untouched, None, tmp_path / "nulle-part")
    assert untouched == {"version": "5.0"}
