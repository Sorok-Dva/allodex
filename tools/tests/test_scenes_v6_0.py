"""Tests des crochets 6.0 (`tools/scenes/v6_0.py`) et de l'option `mirror` du manifeste.

Tout est synthétique : aucun accès à l'arbre serveur ni aux clients du jeu.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from tools.extract_menu_scene import ElementSpec, MaterialSpec, Skeleton, build_scene, validate_glb
from tools.scenes import hooks_for
from tools.scenes.v6_0 import HOOKS, material, native_bind_positions, positions
from tools.tests.test_extract_menu_scene import _write_scene_fixture

IDENTITY = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


def _skeleton(inverse_translation: tuple[float, float, float]) -> Skeleton:
    """Deux os à la racine : l'os 0 « par défaut » (palette = translation (0, 0, 1)), l'os 1
    posé en (10, 0, 0) dont la matrice inverse stockée porte un décalage (le placement natif
    que l'export doit cuire)."""
    local = np.zeros((2, 4, 3))
    local[0, :3] = IDENTITY
    local[1, :3] = IDENTITY
    local[1, 3] = (10.0, 0.0, 0.0)
    inverse = np.zeros((2, 4, 3))
    inverse[0, :3] = IDENTITY
    inverse[0, 3] = (0.0, 0.0, 1.0)
    inverse[1, :3] = IDENTITY
    inverse[1, 3] = inverse_translation
    return Skeleton(names=["joint5_joint6", "Train"], parents=[0xFFFF, 0xFFFF],
                    local=local, inverse=inverse, order=[0, 1])


def _object(skeleton: Skeleton | None) -> SimpleNamespace:
    """Deux éléments : « Sky » (sommet 0, os par défaut seul) et « Train » (sommets 1 à 3 :
    os 1, mixte, et os par défaut seul — le cas des sommets du drapeau liés à `joint5_joint6`)."""
    position = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, -5.0], [0.0, 0.0, -5.0], [0.0, 0.0, -5.0]], np.float32)
    mat = MaterialSpec()
    return SimpleNamespace(
        skeleton=skeleton,
        animation=None,
        indices=np.array([0, 0, 0, 1, 2, 3], np.uint32),
        doc=SimpleNamespace(elements=[ElementSpec("Sky", 0, 3, 0, 1, mat), ElementSpec("Train", 3, 6, 1, 4, mat)]),
        vertices={
            "position": position,
            # indices = décalages dans la palette (3 par os) ; 255 = emplacement inutilisé
            "indices": np.array([[0, 255, 255, 255], [3, 255, 255, 255], [0, 3, 255, 255], [0, 255, 255, 255]], np.uint8),
            "weights": np.array([[255, 0, 0, 0], [255, 0, 0, 0], [128, 128, 0, 0], [255, 0, 0, 0]], np.uint8),
        },
    )


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


def test_native_bind_positions_bakes_the_bind_palette_except_for_the_default_joint():
    obj = _object(_skeleton((0.0, 0.0, 2.0)))
    out = native_bind_positions(obj, obj.vertices["position"])
    # Sommet du décor (os 0) : coordonnées stockées, inchangées.
    np.testing.assert_allclose(out[0], [1.0, 2.0, 3.0])
    # Sommet du train (os 1) : bind · inv_stockée = translation (10, 0, 0) + (0, 0, 2).
    np.testing.assert_allclose(out[1], [10.0, 0.0, -3.0], atol=1e-5)
    # Sommet mixte : la palette complète s'applique (moitié os 0 → (0, 0, -4), moitié os 1).
    np.testing.assert_allclose(out[2], [5.0, 0.0, -3.5], atol=0.05)  # poids 128/255 ≈ 0,502
    # Sommet du train lié au seul os par défaut : l'élément est posé, il suit la palette aussi.
    np.testing.assert_allclose(out[3], [0.0, 0.0, -4.0], atol=1e-5)
    assert out.dtype == np.float32


def test_positions_hook_only_touches_the_menu_geometry():
    obj = _object(_skeleton((0.0, 0.0, 2.0)))
    stored = obj.vertices["position"]
    assert positions("AMM_Shot01", obj, stored) is stored
    assert positions("Animated_Background_6_0", _object(None), stored) is stored
    baked = positions("Animated_Background_6_0", obj, stored)
    assert baked is not stored
    np.testing.assert_allclose(baked[1], [10.0, 0.0, -3.0], atol=1e-5)


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
