"""8.0 « Immortality » : la statue, la cité blanche et son faisceau de lumière.

La scène tient dans un seul maillage skinné (`AMM_8_0`, 65 éléments nommés) ; le
VisObjectTemplate n'attache aucun composant ni objet d'effet. Ce module ne corrige
qu'une chose : le repère.
"""
from __future__ import annotations

import numpy as np

from tools.scenes import SceneHooks

ROOT = "AMM_8_0"

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


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    if name != ROOT:
        return position
    mirror_object(obj)
    return obj.vertices["position"].astype(np.float32)


HOOKS = SceneHooks(positions=positions)
