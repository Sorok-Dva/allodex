"""6.0 « Broken Chains » : vallée du laboratoire et son manatrain suspendu.

La scène tient dans un seul maillage skinné (`Animated_Background_6_0`, 46 éléments) et
son animation `idle` de 3 000 images (100 s à 30 fps) : drapeau du laboratoire, arbres et
balancement du train sont natifs et passent par le mixeur du lecteur. Le VisObjectTemplate
n'attache aucun objet d'effet et aucun matériau ne porte de vitesse de défilement UV : ce
qui bouge dans le client vient du squelette, rien d'autre.

Deux particularités des données :

* le train et le drapeau sont modelés à l'origine et posés par leur articulation
  (`group1`/`Train`, `group2`/`jointRoot…`) : c'est la palette de **bind** — matrices
  locales du squelette (rotation *et* échelle : `group1` est à 0,81, `group2` à 0,37) ×
  matrice inverse stockée — qui les place sur le câble et sur la coupole. L'export
  recalcule les inverses depuis l'image 0 de l'animation, dont les pistes statiques ne
  portent ni cette rotation ni cette échelle (leur 4ᵉ flottant est l'échelle, lu comme un
  quaternion) : le placement serait annulé, le drapeau déchiré. On cuit donc ici la palette
  de bind dans les sommets concernés, comme pour les drapeaux et pierres de la 7.0
  (`attachment_bind_positions`) ;
* tout le décor (ciel, montagnes, laboratoire, voie…) est skinné à poids 1 sur l'os 0,
  `joint5_joint6`, une articulation du drapeau : sa palette de bind le plierait (rotation
  de 97°) alors que le client montre un paysage intact — un défaut d'export Maya (sommets
  sans influence rattachés au premier os). Ces sommets gardent donc leurs coordonnées
  stockées, et le lecteur (`src/components/scene/MenuScene/v6/v6Landscape.ts`) les fige
  pour qu'ils ne suivent pas le drapeau.
"""
from __future__ import annotations

import numpy as np

from tools.scenes import SceneHooks

# Os « par défaut » des sommets sans influence (voir la docstring) : ses sommets ne
# reçoivent pas la palette de bind.
DEFAULT_JOINT = 0


def material(mat, additive: bool) -> bool:
    """Le BlendEffect additif ne vaut que pour les matériaux transparents.

    Le train est marqué ADD mais non transparent : il est peint opaque, comme en jeu.
    """
    return additive and mat.transparent


def native_bind_positions(obj, position: np.ndarray) -> np.ndarray:
    """Palette de bind native appliquée aux éléments posés par le squelette ; le décor garde
    `position`.

    La sélection se fait **par élément** : dès qu'un de ses sommets pèse sur un autre os
    que l'os par défaut, l'élément est un objet posé (train, drapeau, arbres) et tous ses
    sommets reçoivent la palette — y compris ceux que le drapeau lie à `joint5_joint6`,
    qui est aussi l'un de ses vrais os. Les éléments entièrement sur l'os par défaut sont
    le décor mal skinné : coordonnées stockées.
    """
    from tools.extract_menu_scene import attachment_bind_positions, skin_attributes
    skeleton = obj.skeleton
    joints, weights = skin_attributes(obj.vertices, len(skeleton))
    influenced = ((joints != DEFAULT_JOINT) & (weights > 0)).any(axis=1)
    selected = np.zeros(len(position), bool)
    for element in obj.doc.elements:
        used = np.unique(obj.indices[element.ib0:element.ib1])
        if used.size and influenced[used].any():
            selected[used] = True
    bound = attachment_bind_positions(obj.vertices, skeleton)
    result = position.astype(np.float32).copy()
    result[selected] = bound[selected]
    return result


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    if name != "Animated_Background_6_0" or obj.skeleton is None:
        return position
    return native_bind_positions(obj, position)


HOOKS = SceneHooks(material=material, positions=positions)
