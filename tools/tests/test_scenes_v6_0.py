"""Tests des crochets 6.0 (`tools/scenes/v6_0.py`) et de l'option `mirror` du manifeste.

Tout est synthétique : aucun accès à l'arbre serveur ni aux clients du jeu.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from tools.extract_menu_scene import (ElementSpec, JointTrack, MaterialSpec, SkeletalAnimation, Skeleton,
                                      build_scene, quat_matrix, validate_glb)
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
