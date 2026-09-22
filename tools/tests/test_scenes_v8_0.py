"""Crochets 8.0 : annulation du miroir générique sur la géométrie, le squelette et l'animation."""
import numpy as np

from tools.extract_menu_scene import (ElementSpec, JointTrack, LoadedObject, GeometryDoc, MaterialSpec, Skeleton, SkeletalAnimation,
                                      animated_bounds, quat_matrix, rest_world_matrices)
from tools.scenes import hooks_for
from tools.scenes.v8_0 import HOOKS, bake_halo, mirror_object, positions, restore_static_binds

# Liaison native de `group2` (parent du halo), lue dans le squelette du jeu : les lignes sont
# les colonnes de M = R_z(−5,959°) · diag(0,82770 ; 0,77981 ; 0,83692) — rotation puis échelle
# **non uniforme**, colonnes orthogonales à 7·10⁻¹⁰.
GROUP2_ROWS = np.array([[0.82322991, -0.08592476, 0.0],
                        [0.08095334, 0.77559966, 0.0],
                        [0.0, 0.0, 0.83692002]])
GROUP2_TRANSLATION = np.array([39.697224, -20.435099, 10.728845])
# Le seul flottant d'échelle que la piste figée sait porter : la moyenne géométrique des trois.
GROUP2_TRACK_SCALE = 0.8144219517707825


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
    """Squelette réduit du jeu : VisualSceneNode → group2 → glow_add, dont la piste tourne et
    grossit autour du centre du quad **dans le repère du modèle**.

    `group2` reprend sa liaison native (rotation de 5,959° autour de Z + échelle non uniforme)
    et sa piste entièrement figée, qui n'en retient que la translation et la moyenne
    géométrique des échelles — la copie appauvrie que `restore_static_binds` écarte.
    """
    local = np.zeros((3, 4, 3))
    for i in range(3):
        local[i, :3, :] = np.eye(3)
    local[1, :3, :] = GROUP2_ROWS
    local[1, 3, :] = GROUP2_TRANSLATION
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
    still = JointTrack(name="group2", translation=np.array([GROUP2_TRANSLATION]),
                       rotation=np.array([[0.0, 0.0, 0.0, 1.0]]),
                       animated=False, scale=np.array([GROUP2_TRACK_SCALE]))
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
    restore_static_binds(obj)
    obj.vertices["position"] = bake_halo(obj, obj.vertices["position"])
    # Recalé par monde_repos(glow_add) = liaison complète de group2 : centre fixe.
    expected = GROUP2_ROWS.T @ np.array([41.602, -129.973, 44.921]) + GROUP2_TRANSLATION
    for frame in range(3):
        assert np.allclose(_halo_center(obj, frame), expected, atol=0.05)
    # Le quad grossit bien : demi-largeur 14,5 × 2,33, puis la liaison. Le quad tourne autour
    # de Y, donc un écart en x le reste : le facteur est la composante x de la liaison sur x
    # (0,82323), pas la norme de la colonne (0,82770) qui inclut le petit cisaillement en y.
    facteur_x = (GROUP2_ROWS.T @ np.array([1.0, 0.0, 0.0]))[0]
    low, high = animated_bounds(obj, 2)
    assert np.isclose((high - low)[0] / 2, 14.5 * facteur_x * 2.33, atol=0.05)
    # Le parent natif est conservé.
    assert obj.skeleton.parents[obj.skeleton.names.index("glow_add")] == obj.skeleton.names.index("group2")


def test_the_full_bind_matrix_puts_the_halo_on_the_beam_axis():
    """Chiffres de la scène : le croisement des `Smal_Line_*` est en x = 63,57, l'axe du
    faisceau (`In_Big_*`) en x = 64,26. La piste figée lue telle quelle (rotation à 0, échelle
    uniforme 0,814422) pose le halo 9,9 unités trop à droite ; la liaison complète le ramène
    à 0,15 unité du croisement."""
    point = np.array([41.60149956, -129.9730072, 44.92099953])
    piste = GROUP2_TRACK_SCALE * point + GROUP2_TRANSLATION           # rotation lue à 0
    liaison = GROUP2_ROWS.T @ point + GROUP2_TRANSLATION              # matrice de liaison
    assert np.allclose(piste, [73.5776, -126.2884, 47.3134], atol=1e-3)
    assert np.allclose(liaison, [63.4231, -124.8167, 48.3241], atol=1e-3)
    assert abs(piste[0] - 63.570) > 9.9 and abs(liaison[0] - 63.570) < 0.16
    # La piste figée n'est qu'une copie appauvrie : son échelle est la moyenne géométrique des
    # trois échelles de la liaison, écrite à 10⁻⁸ près.
    axes = np.linalg.norm(GROUP2_ROWS, axis=1)
    assert np.isclose(float(np.prod(axes) ** (1 / 3)), GROUP2_TRACK_SCALE, atol=1e-8)
    assert axes.max() / axes.min() > 1.07  # échelle bel et bien non uniforme


def test_restore_static_binds_drops_only_the_redundant_tracks():
    obj = _halo_object()
    assert restore_static_binds(obj) == ["group2"]
    assert [t.name for t in obj.animation.tracks] == ["glow_add"]  # la piste animée reste
    assert restore_static_binds(obj) == []  # idempotent
    # Une piste figée qui ne recopie *pas* la liaison est conservée telle quelle.
    other = _halo_object()
    other.animation.tracks[0].translation = np.array([[1.0, 2.0, 3.0]])
    assert restore_static_binds(other) == []
    assert [t.name for t in other.animation.tracks] == ["group2", "glow_add"]


def test_restore_static_binds_restores_the_bind_rotation_of_the_rest_pose():
    obj = _halo_object()
    before = rest_world_matrices(obj.skeleton, obj.animation)[1]
    restore_static_binds(obj)
    after = rest_world_matrices(obj.skeleton, obj.animation)[1]
    assert np.allclose(before[:3, :3], GROUP2_TRACK_SCALE * np.eye(3))  # rotation perdue
    assert np.allclose(after[:3, :3], GROUP2_ROWS.T, atol=1e-6)         # liaison retrouvée
    assert np.allclose(after[:3, 3], GROUP2_TRANSLATION)


def test_bake_halo_leaves_objects_without_halo_untouched():
    obj = _object()
    before = obj.vertices["position"].copy()
    assert bake_halo(obj, before).tolist() == before.tolist()


def test_positions_bakes_the_halo_for_the_root_only():
    obj = _halo_object()
    raw = obj.vertices["position"].copy()
    baked = positions("AMM_8_0", obj, raw.copy())
    # Reflété *puis* recalé : le reflet et la liaison commutent (S·M·S · S·v + S·t = S·(M·v + t)),
    # le centre cuit est donc le reflet de la composition native.
    mirror = np.array([-1.0, 1.0, 1.0])
    expected = mirror * (GROUP2_ROWS.T @ raw.mean(axis=0).astype(np.float64) + GROUP2_TRANSLATION)
    assert np.allclose(baked.mean(axis=0), expected, atol=1e-3)
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
