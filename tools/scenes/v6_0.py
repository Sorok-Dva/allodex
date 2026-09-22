"""6.0 « Broken Chains » : vallée du laboratoire et son manatrain suspendu.

La scène tient dans un seul maillage skinné (`Animated_Background_6_0`, 46 éléments) et
son animation `idle` de 3 000 images (100 s à 30 fps) : drapeau du laboratoire, arbres et
balancement du train sont natifs et passent par le mixeur du lecteur. Le VisObjectTemplate
n'attache aucun objet d'effet et aucun matériau ne porte de vitesse de défilement UV : ce
qui bouge dans le client vient du squelette, rien d'autre. Les binaires sont identiques
octet pour octet dans les clients 6.0, 7.0 et 8.0 archivés.

Deux particularités des données, toutes deux sur les trois éléments skinnés (`skinIndex`
0 dans le xdb : `Flag1`, `Train`, `Trees` ; les 43 autres sont le décor peint, `skinIndex`
−1, que l'export générique rattache à une articulation immobile) :

* **les canaux de rotation fixes valent la rotation de bind, pas 0.** Une piste dont les
  trois angles sont fixes stocke trois flottants nuls (c'est vrai dans les cinq versions),
  alors que la matrice locale de bind du squelette porte une rotation franche : 85° autour
  de Z pour `group2` (le mât du drapeau), (56°, −10°, −22°) pour `group1` (le porte-train).
  Le client garde donc la rotation de bind sur ces canaux — sans elle le drapeau, modelé
  le long de X, serait vu de chant et le train pendrait dans le mauvais sens. La
  décomposition ZYX du bind donne d'ailleurs des valeurs rondes exactement sur les canaux
  fixes des pistes mixtes (`Train` : Z = X = 0, Y animé). `restore_bind_rotations` remet
  cette rotation dans les pistes concernées avant l'export ;
* le train et le drapeau sont **modelés à l'origine** et posés par leur articulation : leurs
  matrices inverses stockées sont l'identité, c'est la palette de bind (matrices locales
  du squelette, rotation *et* échelle — `group1` est à 0,81, `group2` à 0,37) qui les place
  sur le câble et sur la coupole. L'export recalcule les inverses depuis l'image 0 de
  l'animation : ce placement serait annulé. On cuit donc la palette de bind dans les
  sommets des éléments skinnés, comme pour les drapeaux et pierres de la 7.0
  (`attachment_bind_positions`) ; à l'image 0 la palette recalculée redonne alors
  exactement `W_bind · inverse_stockée · sommet`, et le balancement du train tourne autour
  de l'axe de son articulation correctement orientée.
"""
from __future__ import annotations

import numpy as np

from tools.scenes import SceneHooks

ROOT = "Animated_Background_6_0"

IDENTITY_QUAT = np.array([0.0, 0.0, 0.0, 1.0])


def material(mat, additive: bool) -> bool:
    """Le BlendEffect additif ne vaut que pour les matériaux transparents.

    Le train est marqué ADD mais non transparent : il est peint opaque, comme en jeu.
    """
    return additive and mat.transparent


def restore_bind_rotations(obj) -> list[str]:
    """Pistes à rotation entièrement fixe (constante à l'identité, les flottants stockés
    étant nuls) : reprend la rotation de bind du squelette. Renvoie les pistes corrigées."""
    from tools.extract_menu_scene import _quat_from_rows
    skeleton, animation = obj.skeleton, obj.animation
    if skeleton is None or animation is None:
        return []
    fixed: list[str] = []
    for track in animation.tracks:
        if track.name not in skeleton.names:
            continue
        rotation = np.asarray(track.rotation, float)
        if not np.allclose(rotation, IDENTITY_QUAT, atol=1e-6):
            continue  # au moins un canal animé (ou une rotation fixe non nulle : rien vu de tel)
        wxyz = _quat_from_rows(skeleton.local[skeleton.names.index(track.name)])
        if np.allclose(wxyz, [1.0, 0.0, 0.0, 0.0], atol=1e-6):
            continue
        track.rotation = np.tile([wxyz[1], wxyz[2], wxyz[3], wxyz[0]], (len(rotation), 1))
        fixed.append(track.name)
    return fixed


def native_bind_positions(obj, position: np.ndarray) -> np.ndarray:
    """Palette de bind native appliquée aux éléments skinnés (`skinIndex` ≥ 0 : train,
    drapeau, arbres) ; le décor peint (`skinIndex` −1) garde `position`."""
    from tools.extract_menu_scene import attachment_bind_positions
    selected = np.zeros(len(position), bool)
    for element in obj.doc.elements:
        if element.skin_index >= 0:
            selected[np.unique(obj.indices[element.ib0:element.ib1])] = True
    bound = attachment_bind_positions(obj.vertices, obj.skeleton)
    result = position.astype(np.float32).copy()
    result[selected] = bound[selected]
    return result


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    if name != ROOT or obj.skeleton is None:
        return position
    restore_bind_rotations(obj)
    return native_bind_positions(obj, position)


HOOKS = SceneHooks(material=material, positions=positions)
