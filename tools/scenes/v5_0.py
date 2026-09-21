"""5.0 « Heart of the World » : la tour-phare dans la brume, et le navire de raid qui la survole.

La scène est un seul objet skinné (`Animated_Background_5_0`, 59 articulations) auquel le
`Raid_Ship` est attaché par le locator `Slot_Special01`. Le navire est piloté par sa propre
animation squelettique de 4001 images (133 s) : il naît à l'échelle 0, traverse le champ en
grandissant puis va se ranger au loin ; la boucle fait revenir ce passage périodiquement.
Ses effets attachés (`/Spells/FX/World/AnimBack_Raid_Ship_*`, `EngineTL01.Malfunction`) sont
des systèmes de particules hors périmètre de l'export.
"""
from __future__ import annotations

import numpy as np

from tools.scenes import SceneHooks


def material(mat, additive: bool) -> bool:
    # Écorces, bielles et quelques feuillages portent `BLEND_EFFECT_ADD` avec
    # `transparent: false` : le client ne les rend pas additifs.
    return additive and mat.transparent


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    """Cuit le repère natif de chaque articulation dans les sommets.

    Le lecteur applique `monde(t) · inverse(monde_repos)` à des sommets supposés en espace
    monde. Or beaucoup d'articulations de la 5.0 (toute la tour, le navire, ses voiles)
    ont des matrices inverses de bind **identité** : leurs sommets sont exprimés dans le
    repère de l'articulation et le client les place avec `monde(t) · inverse_native`. On
    remplace donc chaque sommet par `monde_repos · inverse_native · v` — exactement ce que
    l'export attend — sans quoi la roue de la tour, les phares ou les halos s'empilent à
    l'origine et le navire reste posé sur son locator, à l'échelle 1.
    """
    from tools.extract_menu_scene import rest_world_matrices, skin_attributes
    skeleton = obj.skeleton
    if skeleton is None or "indices" not in obj.vertices or "weights" not in obj.vertices:
        return position
    world = rest_world_matrices(skeleton, obj.animation)
    inverse = np.tile(np.eye(4), (len(skeleton), 1, 1))
    inverse[:, :3, :] = skeleton.inverse.transpose(0, 2, 1)
    palette = world @ inverse
    joints, weights = skin_attributes(obj.vertices, len(skeleton))
    points = np.column_stack((position.astype(np.float64), np.ones(len(position))))
    out = np.zeros_like(points)
    for slot in range(4):
        out += np.einsum("nij,nj->ni", palette[joints[:, slot]], points) * (weights[:, slot] / 255.0)[:, None]
    return out[:, :3].astype(np.float32)


HOOKS = SceneHooks(material=material, positions=positions)
