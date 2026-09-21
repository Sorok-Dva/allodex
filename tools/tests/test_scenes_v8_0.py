"""Crochets 8.0 : annulation du miroir générique sur la géométrie, le squelette et l'animation."""
import numpy as np

from tools.extract_menu_scene import (JointTrack, LoadedObject, GeometryDoc, Skeleton, SkeletalAnimation,
                                      quat_matrix, rest_world_matrices)
from tools.scenes import hooks_for
from tools.scenes.v8_0 import HOOKS, mirror_object, positions


def _object(name: str = "AMM_8_0") -> LoadedObject:
    # Une articulation tournée de 90° autour de Z, décalée en X, dont dépend un sommet.
    q = np.array([0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)])  # x, y, z, w
    local = np.zeros((1, 4, 3))
    local[0, :3, :] = quat_matrix(q).T  # lignes = vecteurs de base
    local[0, 3, :] = [10.0, 2.0, 3.0]
    skeleton = Skeleton(names=["joint"], parents=[65535], local=local, inverse=local.copy(), order=[0])
    animation = SkeletalAnimation(fps=30, frames=2, tracks=[JointTrack(
        name="joint", translation=np.array([[10.0, 2.0, 3.0], [12.0, 2.0, 3.0]]),
        rotation=np.array([q, q]), animated=True)])
    return LoadedObject(name=name, doc=GeometryDoc(),
                        vertices={"position": np.array([[5.0, -1.0, 7.0], [-2.0, 4.0, 0.0]], np.float32)},
                        indices=np.array([0, 1, 1], np.uint32), skeleton=skeleton, animation=animation)


def test_hooks_are_registered_for_8_0():
    assert hooks_for("8.0") is HOOKS
    assert HOOKS.positions is positions
    assert HOOKS.material is None and HOOKS.extra_roots is None and HOOKS.after_export is None


def test_positions_mirror_x_for_the_root_only():
    obj = _object()
    out = positions("AMM_8_0", obj, obj.vertices["position"].copy())
    assert out.dtype == np.float32
    assert out.tolist() == [[-5.0, -1.0, 7.0], [2.0, 4.0, 0.0]]
    other = _object("AMM_Autre")
    untouched = other.vertices["position"].copy()
    assert positions("AMM_Autre", other, untouched) is untouched


def test_mirror_object_reflects_skeleton_and_curves_consistently():
    obj = _object()
    before = rest_world_matrices(obj.skeleton, None)[0]
    mirror_object(obj)
    after = rest_world_matrices(obj.skeleton, None)[0]
    # Pose de repos réfléchie par le plan X = 0 : S · M · S avec S = diag(-1, 1, 1, 1).
    s = np.diag([-1.0, 1.0, 1.0, 1.0])
    assert np.allclose(after, s @ before @ s)
    track = obj.animation.tracks[0]
    assert track.translation.tolist() == [[-10.0, 2.0, 3.0], [-12.0, 2.0, 3.0]]
    # Rotation de +90° autour de Z → -90° après reflet : la matrice suit la même règle.
    assert np.allclose(quat_matrix(track.rotation[0]), s[:3, :3] @ quat_matrix([0, 0, np.sqrt(.5), np.sqrt(.5)]) @ s[:3, :3])
    assert np.allclose(obj.skeleton.inverse, obj.skeleton.local)


def test_mirror_object_is_applied_once():
    obj = _object()
    mirror_object(obj)
    first = obj.vertices["position"].copy()
    positions("AMM_8_0", obj, first)  # un second passage ne re-reflète pas
    assert obj.vertices["position"].tolist() == first.tolist()
    assert obj.animation.tracks[0].translation[0].tolist() == [-10.0, 2.0, 3.0]
