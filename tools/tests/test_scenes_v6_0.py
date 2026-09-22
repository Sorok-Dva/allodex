"""Tests des crochets 6.0 (`tools/scenes/v6_0.py`), de l'option `mirror` du manifeste et de
la lecture de la table de descripteurs du `(SkeletalAnimation).bin` tel que la 6.0 le range.

Tout est synthétique : aucun accès à l'arbre serveur ni aux clients du jeu.
"""
from __future__ import annotations

import struct
from types import SimpleNamespace

import numpy as np
import pytest

from tools.extract_menu_scene import (ElementSpec, JointTrack, MaterialSpec, SkeletalAnimation, Skeleton,
                                      build_scene, parse_skeletal_animation, quat_matrix,
                                      validate_glb, _read_track_flags)
from tools.scenes import hooks_for
from tools.scenes.v6_0 import HOOKS, material, native_bind_positions, positions, restore_bind_rotations
from tools.tests.test_extract_menu_scene import _write_scene_fixture

IDENTITY = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
# Rotation de 90° autour de Z, lignes = vecteurs de base transformés.
ROT_Z90 = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def _skeleton(inverse_translation: tuple[float, float, float], train_rows: np.ndarray = IDENTITY) -> Skeleton:
    """Deux os à la racine : l'os 0 (une articulation du drapeau, palette = translation (0, 0, 1))
    et l'os 1 « Train » posé en (10, 0, 0) — avec la rotation `train_rows` — dont la matrice
    inverse stockée porte un décalage (le placement natif que l'export doit cuire)."""
    local = np.zeros((2, 4, 3))
    local[0, :3] = IDENTITY
    local[1, :3] = train_rows
    local[1, 3] = (10.0, 0.0, 0.0)
    inverse = np.zeros((2, 4, 3))
    inverse[0, :3] = IDENTITY
    inverse[0, 3] = (0.0, 0.0, 1.0)
    inverse[1, :3] = IDENTITY
    inverse[1, 3] = inverse_translation
    return Skeleton(names=["joint5_joint6", "Train"], parents=[0xFFFF, 0xFFFF],
                    local=local, inverse=inverse, order=[0, 1])


def _object(skeleton: Skeleton | None, animation: SkeletalAnimation | None = None) -> SimpleNamespace:
    """Deux éléments : « Sky » (sommet 0, décor peint : `skinIndex` −1, pondéré sur l'os 0 dans
    le tampon comme dans le vrai fichier) et « Train » (`skinIndex` 0, sommets 1 à 3 : os 1,
    mixte, et os 0 seul — le cas des sommets du drapeau liés à `joint5_joint6`)."""
    position = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, -5.0], [0.0, 0.0, -5.0], [0.0, 0.0, -5.0]], np.float32)
    mat = MaterialSpec()
    return SimpleNamespace(
        skeleton=skeleton,
        animation=animation,
        indices=np.array([0, 0, 0, 1, 2, 3], np.uint32),
        doc=SimpleNamespace(elements=[ElementSpec("Sky", 0, 3, 0, 1, mat, skin_index=-1),
                                      ElementSpec("Train", 3, 6, 1, 4, mat, skin_index=0)]),
        vertices={
            "position": position,
            # indices = décalages dans la palette (3 par os) ; 255 = emplacement inutilisé
            "indices": np.array([[0, 255, 255, 255], [3, 255, 255, 255], [0, 3, 255, 255], [0, 255, 255, 255]], np.uint8),
            "weights": np.array([[255, 0, 0, 0], [255, 0, 0, 0], [128, 128, 0, 0], [255, 0, 0, 0]], np.uint8),
        },
    )


def _track(name: str, frames: int, rotation: np.ndarray | None = None) -> JointTrack:
    rot = np.tile([0.0, 0.0, 0.0, 1.0], (frames, 1)) if rotation is None else rotation
    return JointTrack(name=name, translation=np.zeros((frames, 3)), rotation=rot, animated=False,
                      scale=np.ones(frames))


def test_hooks_are_registered_for_6_0():
    assert hooks_for("6.0") is HOOKS
    assert HOOKS.material is material and HOOKS.positions is positions
    assert HOOKS.extra_roots is None and HOOKS.after_export is None


def test_additive_blend_only_applies_to_transparent_materials():
    train = MaterialSpec(name="Manatrain", blend="BLEND_EFFECT_ADD", transparent=False)
    rays = MaterialSpec(name="Noise01White", blend="BLEND_EFFECT_ADD", transparent=True)
    assert material(train, True) is False
    assert material(rays, True) is True
    assert material(MaterialSpec(transparent=True), False) is False


def test_native_bind_positions_bakes_the_bind_palette_into_skinned_elements_only():
    obj = _object(_skeleton((0.0, 0.0, 2.0)))
    out = native_bind_positions(obj, obj.vertices["position"])
    # Sommet du décor (skinIndex −1) : coordonnées stockées, inchangées.
    np.testing.assert_allclose(out[0], [1.0, 2.0, 3.0])
    # Sommet du train (os 1) : bind · inv_stockée = translation (10, 0, 0) + (0, 0, 2).
    np.testing.assert_allclose(out[1], [10.0, 0.0, -3.0], atol=1e-5)
    # Sommet mixte : la palette complète s'applique (moitié os 0 → (0, 0, -4), moitié os 1).
    np.testing.assert_allclose(out[2], [5.0, 0.0, -3.5], atol=0.05)  # poids 128/255 ≈ 0,502
    # Sommet du train lié au seul os 0 : l'élément est skinné, il suit la palette aussi.
    np.testing.assert_allclose(out[3], [0.0, 0.0, -4.0], atol=1e-5)
    assert out.dtype == np.float32


def test_restore_bind_rotations_replaces_a_fixed_identity_rotation_by_the_bind_one():
    skeleton = _skeleton((0.0, 0.0, 0.0), train_rows=ROT_Z90)
    animated = np.tile([0.0, 0.0, 0.0, 1.0], (3, 1))
    animated[1] = [0.0, 0.0, np.sin(0.1), np.cos(0.1)]  # un canal qui bouge : piste animée
    animation = SkeletalAnimation(fps=30, frames=3, tracks=[_track("joint5_joint6", 3, animated), _track("Train", 3),
                                                            _track("Absent", 3)])
    obj = _object(skeleton, animation)
    assert restore_bind_rotations(obj) == ["Train"]
    train = animation.tracks[1].rotation
    assert train.shape == (3, 4)
    # Le quaternion restitué redonne la matrice de bind (lignes → colonnes : transposée).
    np.testing.assert_allclose(quat_matrix(train[0]), ROT_Z90.T, atol=1e-6)
    # La piste animée et l'os 0 (bind à l'identité) ne sont pas touchés.
    np.testing.assert_allclose(animation.tracks[0].rotation, animated)
    assert restore_bind_rotations(_object(None)) == []


def test_positions_hook_only_touches_the_menu_geometry_and_restores_rotations():
    skeleton = _skeleton((0.0, 0.0, 2.0), train_rows=ROT_Z90)
    animation = SkeletalAnimation(fps=30, frames=2, tracks=[_track("joint5_joint6", 2), _track("Train", 2)])
    obj = _object(skeleton, animation)
    stored = obj.vertices["position"]
    assert positions("AMM_Shot01", obj, stored) is stored
    assert positions("Animated_Background_6_0", _object(None), stored) is stored
    baked = positions("Animated_Background_6_0", obj, stored)
    assert baked is not stored
    # (0, 0, -5) + (0, 0, 2) = (0, 0, -3), tourné de 90° autour de Z (sans effet sur Z) puis posé en (10, 0, 0).
    np.testing.assert_allclose(baked[1], [10.0, 0.0, -3.0], atol=1e-5)
    # La rotation de bind du train est désormais dans la piste : l'export la lira comme pose de repos.
    np.testing.assert_allclose(quat_matrix(animation.tracks[1].rotation[0]), ROT_Z90.T, atol=1e-6)


def test_build_scene_honours_the_mirror_flag(tmp_path):
    from tools.extract_menu_scene import BinSource

    spec, paths = _write_scene_fixture(tmp_path, with_skeleton=False)
    source = BinSource([paths["bin_dir"]], [])
    spec["mirror"] = False
    glb, _meta, _notes = build_scene("test", spec, paths["server_root"], source)
    doc = validate_glb(glb)
    root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
    assert root["name"] == "scene" and root["scale"] == [1.0, 1.0, 1.0]
    del spec["mirror"]
    glb, _meta, _notes = build_scene("test", spec, paths["server_root"], source)
    doc = validate_glb(glb)
    assert doc["nodes"][doc["scenes"][0]["nodes"][0]]["scale"] == [-1.0, 1.0, 1.0]


# --- le blob d'animation de la 6.0 : table de descripteurs ------------------------------------
#
# Les tests génériques (`test_extract_menu_scene.py`) écrivent des blobs *sans* table de
# descripteurs : le découpage y est deviné par `_infer_track_flags`. Or les fichiers du jeu
# en ont une, et c'est elle qui dit ce que le manatrain 6.0 fait. On reconstruit ici la
# disposition exacte du `(SkeletalAnimation).bin` de la 6.0 pour verrouiller sa lecture.

def build_animation_blob_with_descriptors(frames: int, nodes: list[dict]) -> bytes:
    """Blob d'animation avec sa table de descripteurs, disposé comme celui de la 6.0.

    Entête : `u16 fps, u16 nb_images`, pointeur auto-relatif vers les descripteurs en 4,
    puis trois couples `(count, ptr)` en 8/12 (noms), 16/20 (ordre) et 24/28 (une table que
    le décodage n'utilise pas). Corps d'un nœud : nom terminé par 0 et aligné sur 4 octets,
    flottants, puis les courbes. Descripteur (20 octets) : `u16 drapeaux, u16 nb_canaux,
    ptr_courbes, u32 nb_valeurs, ptr_flottants, u32 nb_flottants` — les deux pointeurs sont
    auto-relatifs et encadrent les deux compteurs.

    Un nœud : `{name, flags, floats, curves}`, `curves` = une liste par canal animé.
    """
    n = len(nodes)
    p_names = 32
    p_desc = p_names + 8 * n
    p_bodies = p_desc + 20 * n
    bodies = bytearray()
    layout: list[tuple[int, int, int]] = []  # (adresse du nom, ptr_flottants, ptr_courbes)
    for node in nodes:
        name_at = p_bodies + len(bodies)
        name = node["name"].encode("ascii") + b"\0"
        bodies += name + b"\0" * ((4 - len(name) % 4) % 4)
        floats_at = p_bodies + len(bodies)
        bodies += struct.pack(f"<{len(node['floats'])}f", *node["floats"])
        curves_at = p_bodies + len(bodies)
        for frame in range(frames):
            # Un mot de 16 bits par canal animé : relu en u16 (translation, échelle) ou en
            # i16 (angle, en tours) selon la composante — on écrit donc le motif brut.
            bodies += struct.pack(f"<{len(node['curves'])}H", *(int(c[frame]) & 0xFFFF for c in node["curves"]))
        layout.append((name_at, floats_at, curves_at))
    p_order = p_bodies + len(bodies)
    buf = bytearray(p_bodies) + bodies + bytearray(2 * n)
    struct.pack_into("<HH", buf, 0, 30, frames)
    struct.pack_into("<I", buf, 4, p_desc - 4)
    struct.pack_into("<II", buf, 8, n, p_names - 12)
    struct.pack_into("<II", buf, 16, n, p_order - 20)
    struct.pack_into("<II", buf, 24, n, p_bodies - 28)
    for i, node in enumerate(nodes):
        name_at, floats_at, curves_at = layout[i]
        field = p_names + 8 * i
        struct.pack_into("<II", buf, field, name_at - field, len(node["name"]) + 1)
        struct.pack_into("<H", buf, p_order + 2 * i, i)
        desc = p_desc + 20 * i
        struct.pack_into("<HH", buf, desc, node["flags"], len(node["curves"]))
        struct.pack_into("<I", buf, desc + 4, curves_at - (desc + 4))
        struct.pack_into("<I", buf, desc + 8, frames * len(node["curves"]))
        struct.pack_into("<I", buf, desc + 12, floats_at - (desc + 12))
        struct.pack_into("<I", buf, desc + 16, len(node["floats"]))
    return bytes(buf)


# Les trois nœuds de la 6.0 dont dépend la question « le train parcourt-il son câble ? »,
# avec les drapeaux et les flottants relevés dans le binaire du jeu.
TRAIN_FLAGS = 0b1011111        # seul l'angle Y est animé ; T, S, angles Z et X fixes
TREE_FLAGS = 0b1111001         # Ty et Tz animés ; tout le reste fixe
GROUP1_FLAGS = 0b1111111       # entièrement fixe


def _train_nodes(frames: int) -> list[dict]:
    return [
        # `group1`, le porte-train : aucun canal, la pose relevée dans le binaire.
        {"name": "group1", "flags": GROUP1_FLAGS,
         "floats": [-36.125401, -21.986601, 9.43996, 0.813397, 0.0, 0.0, 0.0], "curves": []},
        # `Train` : translation fixe à l'origine de son articulation, un seul canal d'angle.
        {"name": "Train", "flags": TRAIN_FLAGS, "floats": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
         "curves": [[0, 91, 182, 91, 0, -82, -165, -82][:frames]]},
        # `Tree02_joint6` : Ty et Tz animés, u16 couvrant toute la plage 0…65535.
        {"name": "Tree02_joint6", "flags": TREE_FLAGS,
         "floats": [0.0, 3.82507, 4.332e-06, 8.86143, 3.190e-06, 1.0, 0.0, 0.0, 0.0],
         "curves": [[0, 21845, 43690, 65535, 43690, 21845, 0, 0][:frames],
                    [65535, 43690, 21845, 0, 21845, 43690, 65535, 65535][:frames]]},
    ]


def test_descriptor_table_is_read_at_the_offsets_of_the_game_files():
    """Les deux pointeurs du descripteur sont en 4 et 12, les deux compteurs en 8 et 16 ;
    lus ainsi, ils tombent sur le découpage que `parse_skeletal_animation` déduit du nom."""
    frames = 8
    nodes = _train_nodes(frames)
    blob = build_animation_blob_with_descriptors(frames, nodes)
    p_desc = 4 + struct.unpack_from("<I", blob, 4)[0]
    for i, node in enumerate(nodes):
        desc = p_desc + 20 * i
        flags, channels = struct.unpack_from("<HH", blob, desc)
        ptr_curves = desc + 4 + struct.unpack_from("<I", blob, desc + 4)[0]
        n_values, = struct.unpack_from("<I", blob, desc + 8)
        ptr_floats = desc + 12 + struct.unpack_from("<I", blob, desc + 12)[0]
        n_floats, = struct.unpack_from("<I", blob, desc + 16)
        assert (flags, channels) == (node["flags"], len(node["curves"]))
        assert (n_values, n_floats) == (frames * len(node["curves"]), len(node["floats"]))
        # Les courbes suivent les flottants, comme dans le fichier du jeu.
        assert ptr_curves == ptr_floats + 4 * n_floats
    animation = parse_skeletal_animation(blob)
    assert [t.name for t in animation.tracks] == ["group1", "Train", "Tree02_joint6"]
    assert animation.undecoded == []


def test_the_manatrain_track_only_carries_one_euler_angle():
    """Drapeau 0b1011111 : translation figée à l'origine de l'articulation et un seul canal
    d'angle (±2°). Le train oscille au bout de son câble, il ne le parcourt pas — ce que
    confirme l'`aabb` du xdb, qui est la boîte des éléments skinnés au repos."""
    frames = 8
    animation = parse_skeletal_animation(build_animation_blob_with_descriptors(frames, _train_nodes(frames)))
    group1, train, tree = animation.tracks
    # Le porte-train est entièrement fixe : c'est lui qui pose le train sur le câble.
    assert group1.animated is False
    np.testing.assert_allclose(group1.translation[0], [-36.125401, -21.986601, 9.43996], rtol=1e-6)
    # Le train ne translate pas d'une image à l'autre, et ne tourne qu'autour de Y.
    assert train.animated is True
    np.testing.assert_allclose(train.translation, np.zeros((frames, 3)), atol=1e-9)
    np.testing.assert_allclose(train.rotation[:, [0, 2]], 0.0, atol=1e-9)  # x et z du quaternion
    angles = 2 * np.degrees(np.arcsin(np.abs(train.rotation[:, 1])))
    assert angles.max() == pytest.approx(182 / 32767 * 360, abs=1e-3)
    assert angles.max() < 2.01
    # Les arbres ne font que translater, de quelques dixièmes d'unité, sans tourner.
    assert tree.animated is True
    np.testing.assert_allclose(tree.rotation, np.tile([0.0, 0.0, 0.0, 1.0], (frames, 1)), atol=1e-9)
    span = tree.translation.max(axis=0) - tree.translation.min(axis=0)
    np.testing.assert_allclose(span, [0.0, 0.2839, 0.2091], atol=1e-3)


def test_descriptor_table_beats_the_inference_on_the_manatrain_track():
    """Sans table, le découpage est deviné ; la 6.0 en a une et c'est elle qui fait autorité."""
    frames = 8
    nodes = _train_nodes(frames)
    blob = build_animation_blob_with_descriptors(frames, nodes)
    assert _read_track_flags(blob, len(nodes), frames) == [node["flags"] for node in nodes]
    # Table absente ou incohérente (blobs synthétiques du reste des tests) : `None`.
    assert _read_track_flags(blob, len(nodes), frames + 1) is None
    assert _read_track_flags(blob, 0, frames) is None
