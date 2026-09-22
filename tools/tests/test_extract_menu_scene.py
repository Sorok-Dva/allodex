"""Tests de `tools/extract_menu_scene.py` (export glTF des scènes de menu animées).

Tout se joue sur des tampons synthétiques : les tests ne lisent ni l'arbre serveur ni les
clients du jeu, qui ne sont pas toujours montés.
"""
from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest

from tools.extract_menu_scene import (
    GltfBuilder,
    Skeleton,
    attachment_bind_positions,
    VertexLayout,
    build_scene,
    decode_vertex_buffer,
    parse_geometry_xdb,
    parse_skeletal_animation,
    parse_skeleton,
    read_chunks,
    rest_local,
    rest_world_matrices,
    self_pointer,
    skin_attributes,
    validate_glb,
)

# --- conteneur ------------------------------------------------------------------------------

def make_chunks(payloads: dict[int, bytes], compress: bool = True) -> bytes:
    raw = b"".join(struct.pack("<II", k, len(v)) + v for k, v in payloads.items())
    return zlib.compress(raw) if compress else raw


def test_read_chunks_decompresses_and_splits():
    data = make_chunks({0: b"abcd", 1: b"ef", 3: b"xyz"})
    assert read_chunks(data) == {0: b"abcd", 1: b"ef", 3: b"xyz"}


def test_read_chunks_accepts_uncompressed_payload():
    assert read_chunks(make_chunks({7: b"hello"}, compress=False)) == {7: b"hello"}


def test_read_chunks_stops_on_truncated_chunk():
    raw = struct.pack("<II", 0, 4) + b"ab"  # annonce 4 octets, n'en fournit que 2
    assert read_chunks(raw) == {}


def test_self_pointer_is_relative_to_its_own_offset():
    buf = b"\0" * 8 + struct.pack("<I", 12)
    assert self_pointer(buf, 8) == 20


# --- vertex buffer --------------------------------------------------------------------------

def _vertex(stride: int, pos, uv, normal=(128, 128, 255), color=(10, 20, 30, 255),
            weights=(255, 0, 0, 0), indices=(0, 255, 255, 255)) -> bytes:
    row = bytearray(stride)
    row[0:12] = struct.pack("<3f", *pos)
    row[12:20] = struct.pack("<2f", *uv)
    row[20:23] = bytes(normal)
    row[24:28] = bytes(color)
    if stride >= 36:
        row[28:32] = bytes(weights)
        row[32:36] = bytes(indices)
    return bytes(row)


def test_decode_vertex_buffer_stride_28():
    layout = VertexLayout(stride=28, position=0, texcoord0=12, color=24, normal=20)
    buf = _vertex(28, (1.0, 2.0, 3.0), (0.25, 0.5)) + _vertex(28, (-1.0, 0.0, 4.0), (1.0, 0.0))
    out = decode_vertex_buffer(buf, layout, 2)
    assert out["position"].tolist() == [[1.0, 2.0, 3.0], [-1.0, 0.0, 4.0]]
    assert out["texcoord0"].tolist() == [[0.25, 0.5], [1.0, 0.0]]
    assert out["color"][0].tolist() == [10, 20, 30, 255]
    assert "weights" not in out and "indices" not in out
    assert out["normal"][0] == pytest.approx([0.0, 0.0, 1.0], abs=0.01)


def test_decode_vertex_buffer_stride_36_has_skin():
    layout = VertexLayout(stride=36, position=0, texcoord0=12, color=24, normal=20,
                          weights=28, indices=32)
    buf = _vertex(36, (0.0, 0.0, 0.0), (0.0, 0.0), weights=(200, 55, 0, 0), indices=(0, 3, 255, 255))
    out = decode_vertex_buffer(buf, layout, 1)
    assert out["weights"][0].tolist() == [200, 55, 0, 0]
    assert out["indices"][0].tolist() == [0, 3, 255, 255]


def test_decode_vertex_buffer_rejects_short_buffer():
    layout = VertexLayout(stride=28, position=0)
    with pytest.raises(ValueError):
        decode_vertex_buffer(b"\0" * 27, layout, 1)


def test_skin_attributes_divides_palette_offsets_by_three():
    vertices = {
        "indices": np.array([[0, 3, 6, 255]], np.uint8),
        "weights": np.array([[128, 64, 63, 0]], np.uint8),
    }
    joints, weights = skin_attributes(vertices, 4)
    assert joints[0].tolist() == [0, 1, 2, 0]
    assert int(weights[0].sum()) == 255
    assert weights[0][3] == 0


def test_skin_attributes_falls_back_when_all_weights_are_zero():
    vertices = {
        "indices": np.array([[255, 255, 255, 255]], np.uint8),
        "weights": np.array([[0, 0, 0, 0]], np.uint8),
    }
    joints, weights = skin_attributes(vertices, 2)
    assert weights[0].tolist() == [255, 0, 0, 0]
    assert joints[0].tolist() == [0, 0, 0, 0]


# --- xdb ------------------------------------------------------------------------------------

def test_attachment_bind_positions_keeps_native_scale_and_recenters():
    local = np.array([[[2, 0, 0], [0, 1, 0], [0, 0, 1], [-10, 0, 0]]], dtype=float)
    inverse = np.array([[[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]], dtype=float)
    skeleton = Skeleton(["root"], [-1], local, inverse, [0])
    vertices = {"position": np.array([[6, 2, 3]], dtype=float),
                "indices": np.array([[0, 255, 255, 255]], np.uint8),
                "weights": np.array([[255, 0, 0, 0]], np.uint8)}
    assert attachment_bind_positions(vertices, skeleton).tolist() == [[2, 2, 3]]
    vertices = {key: np.repeat(value, 2, axis=0) for key, value in vertices.items()}
    assert attachment_bind_positions(vertices, skeleton, np.array([0])).tolist() == [[2, 2, 3], [6, 2, 3]]
    assert vertices["position"].tolist() == [[6, 2, 3], [6, 2, 3]]  # tampon original conservé


def test_v7_opaque_material_does_not_inherit_additive_blending(tmp_path):
    from tools.extract_menu_scene import BinSource
    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=False)
    path = paths["server_root"] / "World/MainMenu/Animated_Background_Test/Demo.(Geometry).xdb"
    path.write_text(path.read_text().replace('<transparent>true</transparent>', '<transparent>false</transparent>'))
    glb, _, _ = build_scene("7.0", spec, paths["server_root"], BinSource([paths["bin_dir"]], []))
    doc = validate_glb(glb)
    material = doc["materials"][doc["meshes"][0]["primitives"][0]["material"]]
    assert material["alphaMode"] == "OPAQUE"
    assert material.get("extras", {}).get("blend") != "add"

GEOMETRY_XDB = """<?xml version="1.0" encoding="UTF-8" ?>
<Geometry>
    <SkeletalAnimation href="/World/MainMenu/X/Demo.(SkeletalAnimation).xdb#xpointer(/a)"/>
    <aabb><center x="0" y="0" z="0"/><extents x="10" y="20" z="30"/></aabb>
    <geometryBox><center x="1" y="2" z="3"/><extents x="4" y="5" z="6"/></geometryBox>
    <indexBuffer><localID>1</localID><size>12</size></indexBuffer>
    <vertexBuffer><localID>0</localID><size>84</size></vertexBuffer>
    <skeleton><localID>2</localID><size>128</size></skeleton>
    <sceneNodes>
        <Item>
            <name>Slot_Special01</name>
            <rotation x="0" y="0" z="0" w="1"/>
            <position x="1.5" y="-2.5" z="3.5"/>
            <scale>2</scale>
        </Item>
    </sceneNodes>
    <vertexDeclarations>
        <Item>
            <color><offset>24</offset><type>COLOR4</type></color>
            <indices><offset>32</offset><type>UBYTE4</type></indices>
            <normal><offset>20</offset><type>COLOR4</type></normal>
            <position><offset>0</offset><type>FLOAT3</type></position>
            <stride>36</stride>
            <tangent><offset>255</offset><type>UNUSED</type></tangent>
            <texcoord0><offset>12</offset><type>FLOAT2</type></texcoord0>
            <weights><offset>28</offset><type>COLOR4</type></weights>
        </Item>
    </vertexDeclarations>
    <modelElements>
        <Item>
            <lods><Item>
                <indexBufferBegin>0</indexBufferBegin>
                <indexBufferEnd>6</indexBufferEnd>
                <vertexBufferBegin>0</vertexBufferBegin>
                <vertexBufferEnd>3</vertexBufferEnd>
            </Item></lods>
            <material>
                <BlendEffect>BLEND_EFFECT_ADD</BlendEffect>
                <diffuseTexture href="/World/T.(Texture).xdb#xpointer(/t)"/>
                <transparencyModifier>0.5</transparencyModifier>
                <transparent>true</transparent>
                <visible>true</visible>
            </material>
            <materialName>Glow</materialName>
            <name>Engine</name>
        </Item>
        <Item>
            <lods><Item>
                <indexBufferBegin>6</indexBufferBegin>
                <indexBufferEnd>12</indexBufferEnd>
                <vertexBufferBegin>3</vertexBufferBegin>
                <vertexBufferEnd>6</vertexBufferEnd>
            </Item></lods>
            <material>
                <BlendEffect>BLEND_EFFECT_ALPHA</BlendEffect>
                <visible>false</visible>
            </material>
            <materialName>Hidden</materialName>
            <name>Hull</name>
        </Item>
    </modelElements>
</Geometry>
"""


def test_parse_geometry_xdb_keeps_native_uv_scroll():
    text = GEOMETRY_XDB.replace('<transparencyModifier>0.5</transparencyModifier>',
        '<transparencyModifier>0.5</transparencyModifier><scrollRGB>true</scrollRGB>'
        '<uTranslateSpeed>-0.05</uTranslateSpeed><vTranslateSpeed>0.02</vTranslateSpeed>')
    material = parse_geometry_xdb(text).elements[0].material
    assert material.uv_scroll == (-0.05, 0.02)


def test_parse_geometry_xdb_reads_elements_and_materials():
    doc = parse_geometry_xdb(GEOMETRY_XDB)
    assert len(doc.elements) == 2
    first = doc.elements[0]
    assert (first.ib0, first.ib1, first.vb0, first.vb1) == (0, 6, 0, 3)
    assert first.material.texture.startswith("/World/T.(Texture).xdb")
    assert first.material.blend == "BLEND_EFFECT_ADD"
    assert first.material.transparent is True
    assert first.material.alpha == pytest.approx(0.5)
    assert doc.elements[1].material.visible is False
    assert doc.vertex_count == 6
    assert doc.skeleton_id == 2
    assert doc.animation_href.endswith("#xpointer(/a)")


def test_parse_geometry_xdb_reads_layout_and_locators():
    doc = parse_geometry_xdb(GEOMETRY_XDB)
    layout = doc.layouts[0]
    assert layout.stride == 36 and layout.skinned
    assert (layout.position, layout.texcoord0, layout.color) == (0, 12, 24)
    locator = doc.locators[0]
    assert locator.name == "Slot_Special01"
    assert locator.position == (1.5, -2.5, 3.5)
    assert locator.scale == 2.0
    assert doc.aabb[1].tolist() == [10.0, 20.0, 30.0]


# --- squelette et animation ------------------------------------------------------------------

def _pointer(target: int, field: int) -> int:
    """Valeur à écrire en `field` pour que le pointeur auto-relatif désigne `target`."""
    return target - field


def build_skeleton_blob(names: list[str], parents: list[int],
                        locals_: list[tuple[tuple, tuple]]) -> bytes:
    """Squelette synthétique : entête de 4 pointeurs, puis les 4 tables."""
    n = len(names)
    header = 32
    p_inverse = header
    p_names = p_inverse + 52 * n
    p_local = p_names + 8 * n
    p_order = p_local + 48 * n
    p_strings = p_order + 2 * n
    buf = bytearray(p_strings)
    struct.pack_into("<8I", buf, 0,
                     _pointer(p_inverse, 0), n,
                     _pointer(p_names, 8), n,
                     _pointer(p_order, 16), n,
                     _pointer(p_local, 24), n)
    strings = bytearray()
    for i, name in enumerate(names):
        rows, translation = locals_[i]
        # matrice inverse de bind : translation opposée, rotation identité
        struct.pack_into("<12f", buf, p_inverse + 52 * i,
                         1, 0, 0, 0, 1, 0, 0, 0, 1, *(-np.asarray(translation)))
        struct.pack_into("<I", buf, p_inverse + 52 * i + 48, parents[i])
        struct.pack_into("<12f", buf, p_local + 48 * i, *rows, *translation)
        offset = p_strings + len(strings)
        struct.pack_into("<II", buf, p_names + 8 * i,
                         _pointer(offset, p_names + 8 * i), len(name) + 1)
        strings += name.encode("ascii") + b"\0"
        struct.pack_into("<H", buf, p_order + 2 * i, i)
    return bytes(buf) + bytes(strings)


IDENTITY_ROWS = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def test_parse_skeleton_reads_names_parents_and_transforms():
    blob = build_skeleton_blob(
        ["Root", "Arm"], [0xFFFF, 0],
        [(IDENTITY_ROWS, (0.0, 0.0, 0.0)), (IDENTITY_ROWS, (1.0, 2.0, 3.0))])
    skeleton = parse_skeleton(blob)
    assert skeleton.names == ["Root", "Arm"]
    assert skeleton.parents == [0xFFFF, 0]
    assert skeleton.local[1][3].tolist() == [1.0, 2.0, 3.0]
    assert skeleton.topological_order() == [0, 1]


def test_rest_world_matrices_chains_parents():
    blob = build_skeleton_blob(
        ["Root", "Arm"], [0xFFFF, 0],
        [(IDENTITY_ROWS, (0.0, 0.0, 5.0)), (IDENTITY_ROWS, (1.0, 0.0, 0.0))])
    world = rest_world_matrices(parse_skeleton(blob), None)
    assert world[1][:3, 3].tolist() == [1.0, 0.0, 5.0]


def test_rest_local_keeps_a_non_uniform_bind_scale():
    """Une liaison `R · diag(sx, sy, sz)` garde ses trois échelles.

    Les lignes stockées sont les colonnes de la matrice : leurs normes sont les échelles.
    Seul `group2` de la 8.0 en a de différentes (0,8277 / 0,7798 / 0,8369) ; partout ailleurs
    les trois sont égales et la pose de repos est inchangée.
    """
    rows = (2.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 4.0)
    blob = build_skeleton_blob(["Root"], [0xFFFF], [(rows, (1.0, 2.0, 3.0))])
    skeleton = parse_skeleton(blob)
    _t, _q, scale = rest_local(skeleton, None, 0)
    assert np.allclose(scale, [2.0, 3.0, 4.0])
    world = rest_world_matrices(skeleton, None)
    assert np.allclose(world[0][:3, :3], np.diag([2.0, 3.0, 4.0]))
    # Échelle isotrope : le vecteur reste constant, comme avant.
    uniform = parse_skeleton(build_skeleton_blob(
        ["Root"], [0xFFFF], [((5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 5.0), (0.0, 0.0, 0.0))]))
    assert np.allclose(rest_local(uniform, None, 0)[2], [5.0, 5.0, 5.0])


def test_rest_local_clamps_each_axis_of_a_degenerate_scale():
    rows = (0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    skeleton = parse_skeleton(build_skeleton_blob(["Root"], [0xFFFF], [(rows, (0.0, 0.0, 0.0))]))
    scale = rest_local(skeleton, None, 0)[2]
    assert scale.tolist() == [1.0, 1.0, 1.0]  # une ligne nulle retombe sur 1 (`_bind_scales`)
    assert np.linalg.det(rest_world_matrices(skeleton, None)[0]) != 0


def build_animation_blob(frames: int, nodes: list[dict]) -> bytes:
    """Animation synthétique.

    Chaque nœud : `{name, translation: [valeur | (base, échelle)], rotation: [valeur | None],
    curves: [[…]]}` — `None` (rotation) et les couples (translation) marquent les composantes
    animées, dont les valeurs par image sont données dans `curves`, dans l'ordre translation
    puis rotation.
    """
    n = len(nodes)
    p_names = 32
    p_nodes = p_names + 8 * n
    bodies = bytearray()
    offsets = []
    for node in nodes:
        offsets.append(p_nodes + len(bodies))
        name = node["name"].encode("ascii") + b"\0"
        bodies += name + b"\0" * ((4 - len(name) % 4) % 4)
        floats: list[float] = []
        for slot in node["translation"]:
            floats += list(slot) if isinstance(slot, tuple) else [slot]
        floats += [v for v in node["rotation"] if v is not None]
        bodies += struct.pack(f"<{len(floats)}f", *floats)
        curves = node.get("curves") or []
        if curves:
            for frame in range(frames):
                bodies += struct.pack(f"<{len(curves)}h", *(int(c[frame]) for c in curves))
            bodies += b"\0" * ((4 - len(bodies) % 4) % 4)
    p_order = p_nodes + len(bodies)
    buf = bytearray(p_nodes) + bodies + bytearray(2 * n)
    struct.pack_into("<HHI", buf, 0, 30, frames, 0)
    struct.pack_into("<II", buf, 8, n, _pointer(p_names, 12))
    struct.pack_into("<II", buf, 16, n, _pointer(p_order, 20))
    struct.pack_into("<II", buf, 24, n, _pointer(p_nodes, 28))
    for i, node in enumerate(nodes):
        field = p_names + 8 * i
        struct.pack_into("<II", buf, field, _pointer(offsets[i], field), len(node["name"]) + 1)
        struct.pack_into("<H", buf, p_order + 2 * i, i)
    return bytes(buf)


def test_parse_skeletal_animation_static_node():
    blob = build_animation_blob(4, [{
        "name": "Root",
        "translation": [1.0, 2.0, 3.0],
        "rotation": [1.0, 0.0, 0.0, 0.0],
    }])
    animation = parse_skeletal_animation(blob)
    assert (animation.fps, animation.frames) == (30, 4)
    track = animation.tracks[0]
    assert track.animated is False
    assert track.translation[0].tolist() == [1.0, 2.0, 3.0]
    assert track.rotation[0].tolist() == [0.0, 0.0, 0.0, 1.0]  # (x, y, z, w)
    assert animation.undecoded == []


def test_parse_skeletal_animation_rotation_curve():
    """3 angles animés : l'échelle reste fixe (1.0), le premier emplacement tourne autour de Z
    (entiers 16 bits en tours), les deux autres restent à zéro."""
    frames = 8
    curves = [[0, 1000, 2000, 3276, 4500, 6553, 8000, 9830], [0] * frames, [0] * frames]
    blob = build_animation_blob(frames, [{
        "name": "flag",
        "translation": [0.0, 0.0, 0.0],
        "rotation": [1.0, None, None, None],
        "curves": curves,
    }])
    track = parse_skeletal_animation(blob).tracks[0]
    assert track.animated is True
    assert track.rotation.shape == (frames, 4)
    assert track.rotation[0].tolist() == pytest.approx([0.0, 0.0, 0.0, 1.0])
    # z croît (1000/32767 tour ≈ 11°, 9830/32767 ≈ 108°), x et y restent nuls, la norme unitaire
    assert track.rotation[7][2] > track.rotation[1][2] > 0
    assert track.rotation[7][:2].tolist() == pytest.approx([0.0, 0.0])
    assert track.rotation[1][2] == pytest.approx(np.sin(np.pi * 1000 / 32767), abs=1e-6)
    assert track.scale.tolist() == [1.0] * frames
    assert float(np.linalg.norm(track.rotation[7])) == pytest.approx(1.0, abs=1e-5)
    assert track.translation.shape == (frames, 3)


def test_parse_skeletal_animation_translation_curve_uses_unsigned_values():
    """Un axe animé porte (base, échelle) et des entiers 16 bits **non signés**."""
    frames = 8
    blob = build_animation_blob(frames, [{
        "name": "ship",
        "translation": [(10.0, 0.001), 5.0, -5.0],
        "rotation": [1.0, 0.0, 0.0, 0.0],
        "curves": [[0, 1000, 2000, 3000, 4000, 5000, 6000, -1]],  # -1 relu en u16 = 65535
    }])
    track = parse_skeletal_animation(blob).tracks[0]
    assert track.translation[0].tolist() == pytest.approx([10.0, 5.0, -5.0])
    assert track.translation[1][0] == pytest.approx(11.0)
    assert track.translation[7][0] == pytest.approx(10.0 + 65535 * 0.001)
    assert track.translation[:, 1].tolist() == [5.0] * frames


def test_parse_skeletal_animation_rejects_absurd_translation_span():
    """Sans garde-fou, un flottant de coordonnée peut passer pour une échelle."""
    blob = build_animation_blob(8, [{
        "name": "ship",
        "translation": [(10.0, 0.5), 5.0, -5.0],
        "rotation": [1.0, 0.0, 0.0, 0.0],
        "curves": [[0, 1000, 2000, 3000, 4000, 5000, 6000, 7000]],
    }])
    track = parse_skeletal_animation(blob, max_span=100.0).tracks[0]
    assert track.animated is False  # découpage refusé : le nœud retombe sur sa pose fixe


# --- écriture glTF ----------------------------------------------------------------------------

def test_gltf_builder_produces_structurally_valid_glb():
    builder = GltfBuilder()
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    acc = builder.add_accessor(positions, "VEC3", "f32", target=34962, minmax=True)
    idx = builder.add_accessor(np.array([0, 1, 2], np.uint32), "SCALAR", "u32", target=34963)
    builder.json["meshes"].append(
        {"primitives": [{"attributes": {"POSITION": acc}, "indices": idx, "mode": 4}]})
    builder.json["scenes"][0]["nodes"].append(builder.add_node({"mesh": 0}))
    glb = builder.to_glb()
    doc = validate_glb(glb)
    assert doc["accessors"][acc]["min"] == [0.0, 0.0, 0.0]
    assert doc["accessors"][acc]["max"] == [1.0, 1.0, 0.0]


def test_glb_chunks_are_padded_to_four_bytes():
    builder = GltfBuilder()
    builder.add_accessor(np.zeros((1, 3), np.float32), "VEC3", "f32")
    glb = builder.to_glb()
    magic, version, total = struct.unpack_from("<III", glb, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(glb)
    offset = 12
    seen = []
    while offset + 8 <= len(glb):
        length, kind = struct.unpack_from("<II", glb, offset)
        assert length % 4 == 0, "chunk non aligné sur 4 octets"
        seen.append(kind)
        offset += 8 + length
    assert seen[0] == 0x4E4F534A and 0x004E4942 in seen


def test_validate_glb_rejects_accessor_outside_its_buffer_view():
    builder = GltfBuilder()
    builder.add_accessor(np.zeros((2, 3), np.float32), "VEC3", "f32")
    builder.json["accessors"][0]["count"] = 99
    with pytest.raises(ValueError, match="accesseur"):
        validate_glb(builder.to_glb())


def test_validate_glb_rejects_buffer_view_outside_buffer():
    builder = GltfBuilder()
    builder.add_accessor(np.zeros((2, 3), np.float32), "VEC3", "f32")
    builder.json["bufferViews"][0]["byteLength"] = 10_000
    with pytest.raises(ValueError, match="bufferView"):
        validate_glb(builder.to_glb())


def test_validate_glb_rejects_truncated_file():
    with pytest.raises(ValueError):
        validate_glb(b"\0" * 8)


def test_validate_glb_rejects_wrong_magic():
    builder = GltfBuilder()
    glb = bytearray(builder.to_glb())
    glb[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="magic"):
        validate_glb(bytes(glb))


# --- scène complète ---------------------------------------------------------------------------

def _write_scene_fixture(tmp_path, with_skeleton: bool) -> tuple[dict, dict]:
    """Écrit un arbre serveur minimal (xdb + .bin) et renvoie (spec, kwargs de build_scene)."""
    directory = "Animated_Background_Test"
    root = tmp_path / "server" / "World" / "MainMenu" / directory
    root.mkdir(parents=True)
    xdb = GEOMETRY_XDB
    if not with_skeleton:
        xdb = xdb.replace("<skeleton><localID>2</localID><size>128</size></skeleton>", "")
        xdb = xdb.replace(
            '<SkeletalAnimation href="/World/MainMenu/X/Demo.(SkeletalAnimation).xdb#xpointer(/a)"/>',
            "")
    (root / "Demo.(Geometry).xdb").write_text(xdb, encoding="utf-8")

    layout = VertexLayout(stride=36, position=0, texcoord0=12, color=24, normal=20,
                          weights=28, indices=32)
    vertices = b"".join(
        _vertex(36, pos, (0.0, 0.0), color=(0, 0, 0, 255), weights=(255, 0, 0, 0),
                indices=(3, 255, 255, 255))
        for pos in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1)])
    indices = struct.pack("<12H", 0, 1, 2, 0, 2, 1, 3, 4, 5, 3, 5, 4)
    payloads = {0: vertices, 1: indices}
    if with_skeleton:
        payloads[2] = build_skeleton_blob(
            ["Root", "Arm"], [0xFFFF, 0],
            [(IDENTITY_ROWS, (0.0, 0.0, 0.0)), (IDENTITY_ROWS, (0.0, 0.0, 1.0))])
    bin_dir = tmp_path / "bins" / "World" / "MainMenu" / directory
    bin_dir.mkdir(parents=True)
    (bin_dir / "Demo.(Geometry).bin").write_bytes(make_chunks(payloads))
    if with_skeleton:
        animation = build_animation_blob(8, [
            {"name": "Root", "translation": [0.0, 0.0, 0.0], "rotation": [1.0, 0.0, 0.0, 0.0]},
            {"name": "Arm", "translation": [0.0, 0.0, 1.0], "rotation": [1.0, None, None, None],
             "curves": [[0, 500, 1000, 1500, 2000, 2500, 3000, 3500], [0] * 8, [0] * 8]},
        ])
        (bin_dir / "Demo.(SkeletalAnimation).bin").write_bytes(make_chunks({0: animation}))
    spec = {
        "dir": directory,
        "roots": ["Demo"],
        "up": [0, 0, 1],
        "background": "#102030",
        "camera": {"position": [0, 10, 0], "target": [0, 0, 0], "fov": 45},
    }
    return spec, {"server_root": tmp_path / "server", "bin_dir": tmp_path / "bins"}


def test_build_scene_writes_a_valid_glb_with_skin_and_animation(tmp_path):
    from tools.extract_menu_scene import BinSource

    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=True)
    source = BinSource([paths["bin_dir"]], [])
    glb, meta, notes = build_scene("test", spec, paths["server_root"], source)
    doc = validate_glb(glb)
    assert meta["camera"] == spec["camera"]
    assert meta["up"] == [0, 0, 1]
    assert meta["stats"]["triangles"] == 2  # le second élément est `visible: false`
    assert meta["animations"] == ["Demo"]
    assert doc["skins"] and doc["animations"]
    primitive = doc["meshes"][0]["primitives"][0]
    assert primitive["extras"]["element"]  # ciblage des effets, indépendant du matériau partagé
    assert primitive["extras"]["uvScroll"] == [0, 0]
    assert {"POSITION", "TEXCOORD_0", "COLOR_0", "JOINTS_0", "WEIGHTS_0"} <= set(primitive["attributes"])
    material = doc["materials"][primitive["material"]]
    assert material["alphaMode"] == "BLEND"
    assert material["extras"] == {"blend": "add"}
    assert "KHR_materials_unlit" in material["extensions"]
    assert "KHR_materials_unlit" in doc["extensionsUsed"]


def test_build_scene_mirrors_the_left_handed_world(tmp_path):
    from tools.extract_menu_scene import BinSource

    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=False)
    glb, _meta, _notes = build_scene("test", spec, paths["server_root"],
                                     BinSource([paths["bin_dir"]], []))
    doc = validate_glb(glb)
    root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
    assert root["scale"] == [-1.0, 1.0, 1.0]


def test_build_scene_black_vertex_colour_becomes_untinted(tmp_path):
    from tools.extract_menu_scene import BinSource

    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=False)
    glb, _meta, _notes = build_scene("test", spec, paths["server_root"],
                                     BinSource([paths["bin_dir"]], []))
    doc = validate_glb(glb)
    accessor = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"]]
    view = doc["bufferViews"][accessor["bufferView"]]
    offset = 12
    while struct.unpack_from("<II", glb, offset)[1] != 0x004E4942:
        length = struct.unpack_from("<II", glb, offset)[0]
        offset += 8 + length
    blob = glb[offset + 8:]
    start = view.get("byteOffset", 0)
    assert list(blob[start:start + 4]) == [255, 255, 255, 255]
    assert accessor["normalized"] is True


def test_build_scene_reports_a_missing_geometry(tmp_path):
    from tools.extract_menu_scene import BinSource

    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=False)
    spec = dict(spec, roots=["Absent"])
    glb, meta, notes = build_scene("test", spec, paths["server_root"],
                                   BinSource([paths["bin_dir"]], []))
    validate_glb(glb)
    assert any("Absent" in note for note in notes)
    assert meta["stats"]["objects"] == 0


def test_run_skips_unpublished_versions_and_removes_a_previous_drop(tmp_path, monkeypatch):
    from tools import extract_menu_scene as ems

    server = tmp_path / "server"
    (server / "World" / "MainMenu" / "AB").mkdir(parents=True)
    out = tmp_path / "out"
    (out / "4.0").mkdir(parents=True)
    (out / "4.0" / "scene.glb").write_bytes(b"old")
    (out / "4.0" / "scene.json").write_text("{}")
    manifest = {"server_root": str(server), "max_texture": 512,
                "versions": {"4.0": {"dir": "AB", "publish": False, "max_texture": 2048}}}
    called = []
    monkeypatch.setattr(ems, "build_scene", lambda *a, **k: called.append(a) or (b"glb", {"stats": {"triangles": 0, "textures": 0, "animations": 0}}, []))
    monkeypatch.setattr(ems, "validate_glb", lambda glb: None)

    report: list[str] = []
    results = ems.run(manifest, out, report=report)
    assert results == {} and called == []
    assert not (out / "4.0" / "scene.glb").exists() and not (out / "4.0" / "scene.json").exists()
    assert any("non publiée" in line for line in report)

    # `--only` force l'export malgré `publish: false`.
    results = ems.run(manifest, out, only=["4.0"], report=report)
    assert "4.0" in results and (out / "4.0" / "scene.glb").read_bytes() == b"glb"
    assert called[-1][-1] == 2048  # la qualité propre à une version prime sur le défaut global
