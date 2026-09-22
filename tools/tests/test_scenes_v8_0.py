"""Crochets 8.0 : annulation du miroir générique sur la géométrie, le squelette et l'animation."""
import numpy as np

from tools.extract_menu_scene import (ElementSpec, JointTrack, LoadedObject, GeometryDoc, MaterialSpec, Skeleton, SkeletalAnimation,
                                      animated_bounds, quat_matrix, rest_world_matrices)
from tools.scenes import hooks_for
from tools.scenes.v8_0 import HOOKS, bake_halo, mirror_object, positions


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


def _halo_object() -> LoadedObject:
    """Squelette réduit du jeu : VisualSceneNode → group2 (translaté, échelle 0,81) → glow_add,
    dont la piste tourne et grossit autour du centre du quad **dans le repère du modèle**."""
    local = np.zeros((3, 4, 3))
    for i in range(3):
        local[i, :3, :] = np.eye(3)
    local[1, :3, :] *= 0.8144
    local[1, 3, :] = [39.697, -20.435, 10.729]
    inverse = np.zeros((3, 4, 3))
    for i in range(3):
        inverse[i, :3, :] = np.eye(3)  # matrices inverses de bind du jeu : identité pour les trois
    skeleton = Skeleton(names=["VisualSceneNode", "group2", "glow_add"], parents=[65535, 0, 1],
                        local=local, inverse=inverse, order=[0, 1, 2])
    center = np.array([41.602, -129.973, 44.921])
    scales = np.array([1.0, 1.7, 2.33])
    angles = np.radians([0.0, 90.0, 180.0])  # autour de Y (axe de visée)
    rotation = np.stack([[0.0, np.sin(a / 2), 0.0, np.cos(a / 2)] for a in angles])
    translation = np.stack([center - s * (quat_matrix(q) @ center) for s, q in zip(scales, rotation)])
    still = JointTrack(name="group2", translation=np.array([local[1, 3]]), rotation=np.array([[0.0, 0.0, 0.0, 1.0]]),
                       animated=False, scale=np.array([0.8144]))
    halo = JointTrack(name="glow_add", translation=translation, rotation=rotation, animated=True, scale=scales)
    quad = center + np.array([[-14.5, 0.0, -14.5], [14.5, 0.0, -14.5], [14.5, 0.0, 14.5], [-14.5, 0.0, 14.5]])
    doc = GeometryDoc()
    doc.elements.append(ElementSpec(name="glow_add", ib0=0, ib1=6, vb0=0, vb1=4,
                                    material=MaterialSpec(name="Glow04White"), skin_index=0))
    return LoadedObject(name="AMM_8_0", doc=doc,
                        vertices={"position": quad.astype(np.float32),
                                  # emplacement 0 → glow_add (indice 2, rangé ×3 dans le tampon), autres inutilisés
                                  "indices": np.array([[6, 255, 255, 255]] * 4, np.uint8),
                                  "weights": np.array([[255, 0, 0, 0]] * 4, np.uint8)},
                        indices=np.array([0, 1, 2, 0, 2, 3], np.uint32), skeleton=skeleton,
                        animation=SkeletalAnimation(fps=30, frames=3, tracks=[still, halo]))


def _halo_center(obj: LoadedObject, frame: int) -> np.ndarray:
    low, high = animated_bounds(obj, frame)
    return (low + high) / 2


def test_bake_halo_composes_group2_and_keeps_the_glow_centred():
    obj = _halo_object()
    # Sommets en repère d'articulation (inverse native identité) pris pour de l'espace modèle :
    # l'animation fait tourner le quad autour de l'origine de l'articulation → il dérive.
    drift = np.linalg.norm(_halo_center(obj, 2) - _halo_center(obj, 0))
    assert drift > 30
    obj.vertices["position"] = bake_halo(obj, obj.vertices["position"])
    # Recalé par monde_repos(glow_add) = group2 (translation, échelle 0,81) : centre fixe.
    expected = np.array([39.697, -20.435, 10.729]) + 0.8144 * np.array([41.602, -129.973, 44.921])
    for frame in range(3):
        assert np.allclose(_halo_center(obj, frame), expected, atol=0.05)
    # Le quad grossit bien : demi-largeur 14,5 × 0,81 → × 2,33.
    low, high = animated_bounds(obj, 2)
    assert np.isclose((high - low)[0] / 2, 14.5 * 0.8144 * 2.33, atol=0.1)
    # Le parent natif est conservé.
    assert obj.skeleton.parents[obj.skeleton.names.index("glow_add")] == obj.skeleton.names.index("group2")


def test_bake_halo_leaves_objects_without_halo_untouched():
    obj = _object()
    before = obj.vertices["position"].copy()
    assert bake_halo(obj, before).tolist() == before.tolist()


def test_positions_bakes_the_halo_for_the_root_only():
    obj = _halo_object()
    raw = obj.vertices["position"].copy()
    baked = positions("AMM_8_0", obj, raw.copy())
    assert np.linalg.norm(baked.mean(axis=0) - raw.mean(axis=0) * np.array([-1, 1, 1])) > 30  # reflété puis recalé
    other = _halo_object()
    kept = positions("AMM_Autre", other, other.vertices["position"].copy())
    assert kept.tolist() == other.vertices["position"].tolist()


def test_mirror_object_is_applied_once():
    obj = _object()
    mirror_object(obj)
    first = obj.vertices["position"].copy()
    positions("AMM_8_0", obj, first)  # un second passage ne re-reflète pas
    assert obj.vertices["position"].tolist() == first.tolist()
    assert obj.animation.tracks[0].translation[0].tolist() == [-10.0, 2.0, 3.0]
