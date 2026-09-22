"""8.0 « Immortality » : la statue, la cité blanche et son faisceau de lumière.

La scène tient dans un seul maillage skinné (`AMM_8_0`, 65 éléments nommés) ; le
VisObjectTemplate n'attache aucun composant ni objet d'effet. Ce module corrige trois
choses : le repère, la pose des articulations dont la piste est entièrement figée, et le
repère des sommets du halo `glow_add`.
"""
from __future__ import annotations

import numpy as np

from tools.scenes import SceneHooks

ROOT = "AMM_8_0"

# Articulation du halo au sommet du dôme (élément `glow_add`, seul élément `skinIndex 0`
# du faisceau).
HALO_JOINT = "glow_add"

IDENTITY_QUAT = np.array([0.0, 0.0, 0.0, 1.0])

# Reflet du plan X = 0 : signe des composantes d'un vecteur, puis des éléments d'une
# matrice 3×3 rangée en lignes (un élément change de signe quand une seule de ses deux
# coordonnées est l'axe X).
_MIRROR = np.array([-1.0, 1.0, 1.0])
_MIRROR_ROWS = np.outer(_MIRROR, _MIRROR)


def mirror_object(obj) -> None:
    """Reflète en place la géométrie, le squelette et l'animation d'un objet chargé.

    La capture du client (`refs/captures-ui/menu-8.0-frame1.png`) montre la statue à
    gauche et la cité à droite ; or les sommets ont la statue en X négatif et la cité en
    X positif, et les calques de fond sont des arcs concentriques centrés sur
    Y ≈ -400 : la caméra regarde donc +Y, et dans ce sens le nœud miroir générique
    (`scale [-1, 1, 1]`, hérité du calage 7.0) retournerait la scène. On la reflète ici
    une première fois pour que les deux reflets s'annulent et que le `.glb` soit dans le
    bon sens — squelette et courbes compris, sans quoi les arbres pivoteraient autour
    d'articulations placées de l'autre côté.
    """
    if getattr(obj, "mirrored", False):
        return
    obj.mirrored = True
    obj.vertices["position"] = obj.vertices["position"] * _MIRROR
    skeleton = obj.skeleton
    if skeleton is not None:
        for table in (skeleton.local, skeleton.inverse):
            table[:, :3, :] *= _MIRROR_ROWS
            table[:, 3, :] *= _MIRROR
    if obj.animation is not None:
        for track in obj.animation.tracks:
            track.translation = track.translation * _MIRROR
            # Quaternion (x, y, z, w) réfléchi par le plan X = 0 : l'axe garde sa
            # composante X, les deux autres changent de signe.
            track.rotation = track.rotation * np.array([1.0, -1.0, -1.0, 1.0])


def restore_static_binds(obj) -> list[str]:
    """Pistes sans aucun canal animé : le client garde la **matrice locale de liaison**.

    Le format d'animation ne peut pas porter la pose complète d'une telle piste. Vérifié
    sur les 284 pistes des cinq versions : sa translation recopie exactement celle du bind,
    son unique flottant d'échelle vaut la **moyenne géométrique** des trois échelles du bind
    (`group2` : 0,814422 pour 0,82770 × 0,77981 × 0,83692, à 7·10⁻⁹ près) et ses trois angles
    d'Euler sont toujours écrits à 0 — y compris quand le bind porte une rotation franche
    (`Root` 155,5°, `Root_grass` 119,9°, `group2` 5,96°). Une piste figée est donc une copie
    appauvrie du bind : on l'écarte pour que `rest_local` reprenne la matrice du squelette,
    échelle non uniforme comprise. Même règle qu'en 5.0 (`restore_fixed_rotations`) et en
    6.0 (`restore_bind_rotations`), poussée jusqu'à l'échelle.

    Ce que ça change, mesuré sur les sommets dessinés :

    * `group2` porte le seul halo : son centre passe de (73,58 ; −126,29 ; 47,31) à
      (63,42 ; −124,82 ; 48,32), à 0,15 unité du croisement des `Smal_Line_*` (63,57) au
      lieu de 9,94 — le halo revient sur l'axe du faisceau (`In_Big_*` en x = 64,26) ;
      aucun autre sommet dessiné ne bouge (écart nul aux 201 images) ;
    * `Root` et `Root_grass` (rotations pures autour de Y, translation nulle) replacent les
      pivots des arbres et de l'herbe sur la géométrie qu'ils emportent : distance moyenne
      articulation ↔ sommets emportés 188 → 65 unités (`joint9` : 43,4 → 8,6). Le balancement
      natif ne fait que 0,15 à 0,5°, l'écart sur les sommets plafonne à 4,07 unités.

    Renvoie les noms écartés ; idempotent.
    """
    from tools.extract_menu_scene import _bind_scales
    skeleton, animation = obj.skeleton, obj.animation
    if skeleton is None or animation is None:
        return []
    kept: list = []
    dropped: list[str] = []
    for track in animation.tracks:
        index = skeleton.names.index(track.name) if track.name in skeleton.names else None
        scales = None if index is None else _bind_scales(skeleton.local[index])
        # La piste doit bien être la copie appauvrie décrite ci-dessus, sans quoi on la garde.
        redundant = (
            index is not None and not track.animated
            and np.allclose(track.translation[0], skeleton.local[index][3], atol=1e-4)
            and np.allclose(track.rotation[0], IDENTITY_QUAT, atol=1e-6)
            and np.isclose(float(track.scale[0]), float(np.prod(scales) ** (1 / 3)), atol=1e-5)
        )
        (dropped if redundant else kept).append(track.name if redundant else track)
    animation.tracks = kept
    return dropped


def bake_halo(obj, position: np.ndarray) -> np.ndarray:
    """Recale les sommets du halo `glow_add` dans le repère du modèle.

    Sa matrice inverse de bind native est l'identité : ses sommets sont exprimés dans le
    repère de l'articulation, que le client place avec `monde(t) · identité`. L'export,
    lui, recalcule l'inverse depuis la pose de repos et attend des sommets en espace
    modèle : on applique donc `monde_repos(glow_add) · v` — le groupe parent `group2`
    compris, dont la liaison est `R_z(−5,959°) · diag(0,82770 ; 0,77981 ; 0,83692)` puis
    la translation (39,697 ; −20,435 ; 10,729) (colonnes orthogonales à 7·10⁻¹⁰ : c'est
    bien une rotation suivie d'une échelle par axe, pas une matrice quelconque). Sans ce
    recalage, l'animation faisait tourner le quad autour de l'origine de l'articulation,
    à 137 unités de son centre : l'« orbite » qui sortait le halo du cadre.

    La piste de `glow_add` fixe exactement le centre brut du quad
    P = (41,601 ; −129,973 ; 44,921) : `T(f) + s(f)·R(f)·P = P` à 0,029 unité sur les 201
    images. Le halo se pose donc en `monde_repos(group2) · P`, sans dérive (0,02 unité
    d'écart entre les images).
    """
    from tools.extract_menu_scene import rest_world_matrices
    skeleton = obj.skeleton
    if skeleton is None or HALO_JOINT not in skeleton.names:
        return position
    element = next((e for e in obj.doc.elements if e.name == HALO_JOINT), None)
    if element is None:
        return position
    world = rest_world_matrices(skeleton, obj.animation)[skeleton.names.index(HALO_JOINT)]
    selected = np.unique(obj.indices[element.ib0:element.ib1])
    points = np.column_stack((position[selected].astype(np.float64), np.ones(len(selected))))
    position = position.copy()
    position[selected] = (points @ world.T)[:, :3].astype(np.float32)
    return position


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    if name != ROOT:
        return position
    mirror_object(obj)
    restore_static_binds(obj)  # avant la cuisson : elle lit `rest_world_matrices`
    return bake_halo(obj, obj.vertices["position"].astype(np.float32))


HOOKS = SceneHooks(positions=positions)
