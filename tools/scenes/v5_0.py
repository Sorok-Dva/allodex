"""5.0 « Heart of the World » : la tour-phare dans la brume, et le navire de raid qui la survole.

La scène est un seul objet skinné (`Animated_Background_5_0`, 59 articulations) auquel le
`Raid_Ship` est attaché par le locator `Slot_Special01`. Le navire est piloté par sa propre
animation squelettique de 4001 images (133 s) : il naît à l'échelle 0, traverse le champ en
grandissant puis va se ranger au loin — sa pose de bind est cette pose finale (échelle 0,632,
retrouvée à 2·10⁻⁴). Ses effets attachés (`/Spells/FX/World/AnimBack_Raid_Ship_*`,
`EngineTL01.Malfunction`) sont des systèmes de particules hors périmètre de l'export.

Deux corrections de pose, toutes deux lues dans les données :

* **Angles fixes de la pose de bind** (`restore_fixed_rotations`). Dans le blob d'animation,
  un angle d'Euler *fixe* n'est pas écrit (son flottant vaut 0), alors que la matrice locale
  de bind du squelette porte la rotation réelle : `root` (rochers) tourne de ~180°, `root1`
  (grand arbre) aussi, `Tower`/`group5` de 10,4° autour de Z, les bielles ont un Z fixe à 180°,
  la branche `joint9` un Y fixe à 90°. Les angles *animés*, eux, sont absolus et valent ceux du
  bind à l'image 0 (`Tree_08`, `Tree_07`, `joint7`, `joint8`, `joint14`…). On remplace donc
  chaque angle fixe par celui de la pose de bind — dans la branche d'Euler qui s'accorde aux
  angles animés — ce qui redonne exactement (à 24 articulations sur 35 à inverse réelle, les
  autres à moins de 0,3) la pose de bind stockée, et aligne toutes les pièces de la tour sur un
  même axe (X ≈ −52, Y ≈ 24). Sans cela l'arbre est 33 unités trop bas, les rochers passent
  derrière la tour à X = +61 et les pièces de la tour s'étalent sur 14 unités en Y.
* **Repère natif cuit dans les sommets** (`positions`). Toute la tour et le navire ont des
  matrices inverses de bind identité : leurs sommets sont dans le repère de l'articulation.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from tools.scenes import SceneHooks
from tools.scenes.v4_0 import read_sort_mode

DIRECTORY = "Animated_Background_5_0"
GEOMETRIES = ("Animated_Background_5_0", "Raid_Ship")


def material(mat, additive: bool) -> bool:
    # Écorces, bielles et quelques feuillages portent `BLEND_EFFECT_ADD` avec
    # `transparent: false` : le client ne les rend pas additifs.
    return additive and mat.transparent


def euler_zyx(matrix: np.ndarray) -> tuple[float, float, float]:
    """Matrice de rotation (colonnes = base) → angles (az, ay, ax) tels que R = Rz · Ry · Rx."""
    m = np.asarray(matrix, float)
    ay = math.asin(max(-1.0, min(1.0, -m[2, 0])))
    if abs(m[2, 0]) > 1.0 - 1e-9:  # blocage de cardan : Z porte tout, X = 0
        return math.atan2(-m[0, 1], m[1, 1]), ay, 0.0
    return math.atan2(m[1, 0], m[0, 0]), ay, math.atan2(m[2, 1], m[2, 2])


def _wrap(angle: np.ndarray) -> np.ndarray:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _decoded_angles(matrix: np.ndarray) -> np.ndarray:
    """Retrouve les angles que le décodeur a composés : des deux décompositions ZYX d'une
    rotation, celle qui compte le plus d'angles nuls (les composantes fixes valent
    exactement 0 dans les pistes décodées ; une bielle à Y = 98° se lirait sinon
    (180°, 82°, 180°))."""
    a, b, c = euler_zyx(matrix)
    first = _wrap(np.array([a, b, c]))
    second = _wrap(np.array([a + math.pi, math.pi - b, c + math.pi]))
    return second if (np.abs(second) < 1e-6).sum() > (np.abs(first) < 1e-6).sum() else first


def reaches_bind(rotation: np.ndarray, a: float, b: float, c: float, atol: float = 1e-5) -> bool:
    """Une image de la piste porte-t-elle exactement la rotation de bind `(a, b, c)` ?

    Deux quaternions unitaires décrivent la même rotation quand la valeur absolue de leur
    produit scalaire vaut 1. Le seuil est large (10⁻⁵) : sur la 5.0, l'articulation qui
    atteint son bind y arrive à 1,000000 et la plus proche des autres reste à 0,997.
    """
    from tools.extract_menu_scene import _euler_zyx_quaternion
    bind = _euler_zyx_quaternion(np.array([a]), np.array([b]), np.array([c]))[0]
    return bool(np.abs(np.asarray(rotation) @ bind).max() > 1 - atol)


def restore_fixed_rotations(obj) -> list[str]:
    """Remet dans chaque piste les angles d'Euler fixes lus dans la pose de bind du squelette.

    Un angle est tenu pour fixe quand il vaut 0 à toutes les images (le décodeur générique met
    0 aux composantes que le drapeau de la piste déclare fixes). La rotation de bind admet deux
    décompositions ZYX, `(a, b, c)` et `(a + π, π − b, c + π)` : on garde celle avec laquelle la
    piste passe au plus près du bind (les bielles tournent de 98° autour de Y avec un Z fixe à
    180°, décomposition que le premier jet cacherait sous `(0°, 82°, −180°)` ; un genou fléchi
    de 110° à l'image 0 reste sur la branche identité, qu'il frôle à 11°). Renvoie les noms des articulations retouchées ; idempotent.

    Rien à restaurer quand la piste brute **passe déjà par la rotation de bind** : les canaux
    fixes laissés à 0 sont alors les bons, la pose de bind n'étant pas toujours celle de
    l'image 0. C'est le cas de `ship_tail`, la traînée du navire de raid : son bind est
    l'identité et sa piste la tient de l'image 1725 à la fin, exactement la période où son
    échelle vaut 1 ; à l'image 0, où son échelle est nulle donc l'élément invisible, la piste
    porte un demi-tour autour de Z qui faisait choisir la seconde branche et posait 180° sur Y
    et X — la traînée, retournée, se refermait en bulle autour du navire. Dans toute la 5.0,
    `ship_tail` est la seule articulation où ce cas se présente : les autres articulations
    substituées n'atteignent jamais leur bind avec leur piste brute (au mieux 0,997).
    """
    from tools.extract_menu_scene import _bind_scale, _euler_zyx_quaternion, quat_matrix
    skeleton, animation = obj.skeleton, obj.animation
    if skeleton is None or animation is None or getattr(obj, "fixed_rotations_restored", False):
        return []
    obj.fixed_rotations_restored = True
    touched: list[str] = []
    by_name = {name: i for i, name in enumerate(skeleton.names)}
    for track in animation.tracks:
        index = by_name.get(track.name)
        if index is None:
            continue
        angles = np.array([_decoded_angles(quat_matrix(q)) for q in track.rotation])  # (frames, 3)
        fixed = np.all(np.abs(angles) < 1e-6, axis=0)
        if not fixed.any():
            continue
        rows = skeleton.local[index][:3]
        bind = (rows / _bind_scale(rows)).T
        a, b, c = euler_zyx(bind)
        if reaches_bind(track.rotation, a, b, c):
            continue  # la piste brute atteint déjà le bind : les zéros sont les bons
        branches = np.array([[a, b, c], [a + math.pi, math.pi - b, c + math.pi]])
        moving = ~fixed
        if moving.any():
            # Chaque branche donne une famille de rotations (angles animés bruts, fixes du
            # bind) qui passe par le bind quand les angles animés valent ceux de la branche :
            # on garde celle dont la piste **s'en approche le plus** ; l'écart des angles
            # animés à l'image 0 ne départage que les égalités. Ce seul écart trompait sur une
            # charnière très fléchie : le genou gauche de `KaniaMale.Run` (bind identité, X
            # animé de 11° à 110°, 110° à l'image 0) prenait la branche (180°, 180°, 180°),
            # soit un demi-tour de plus sur X — jambe repliée à 160°, pied à hauteur de hanche.
            bind_q = _euler_zyx_quaternion(np.array([a]), np.array([b]), np.array([c]))[0]
            miss = []
            for branch in branches:
                trial = angles.copy()
                trial[:, fixed] = branch[fixed]
                q = _euler_zyx_quaternion(trial[:, 0], trial[:, 1], trial[:, 2])
                miss.append(round(1.0 - float(np.abs(q @ bind_q).max()), 6))
            error = np.abs(_wrap(branches[:, moving] - angles[0, moving])).sum(axis=1)
            chosen = branches[min(range(2), key=lambda k: (miss[k], error[k]))]
        else:
            chosen = branches[0]
        if np.allclose(_wrap(chosen[fixed]), 0.0, atol=1e-6):
            continue  # le bind confirme un angle nul : rien à faire
        angles[:, fixed] = chosen[fixed]
        track.rotation = _euler_zyx_quaternion(angles[:, 0], angles[:, 1], angles[:, 2])
        touched.append(track.name)
    return touched


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    """Cuit le repère natif de chaque articulation dans les sommets.

    Le lecteur applique `monde(t) · inverse(monde_repos)` à des sommets supposés en espace
    monde. Or beaucoup d'articulations de la 5.0 (toute la tour, le navire, ses voiles)
    ont des matrices inverses de bind **identité** : leurs sommets sont exprimés dans le
    repère de l'articulation et le client les place avec `monde(t) · inverse_native`. On
    remplace donc chaque sommet par `monde_repos · inverse_native · v` — exactement ce que
    l'export attend — sans quoi la roue de la tour, les phares ou les halos s'empilent à
    l'origine et le navire reste posé sur son locator, à l'échelle 1. La pose de repos est
    celle de l'image 0 après `restore_fixed_rotations`.

    Les éléments `skinIndex -1` du xdb (coupole de nuages, brumes, soleil, arbres d'amorce)
    ne sont pas skinnés par le client : leurs sommets sont déjà en espace monde et restent
    tels quels — le tampon les lie pourtant à l'articulation 0 (`joint17`, un rocher sous
    `root`, tourné de ~180°), qui les retournerait de l'autre côté de la tour.
    """
    from tools.extract_menu_scene import rest_world_matrices, skin_attributes
    skeleton = obj.skeleton
    if skeleton is None or "indices" not in obj.vertices or "weights" not in obj.vertices:
        return position
    restore_fixed_rotations(obj)
    world = rest_world_matrices(skeleton, obj.animation)
    inverse = np.tile(np.eye(4), (len(skeleton), 1, 1))
    inverse[:, :3, :] = skeleton.inverse.transpose(0, 2, 1)
    palette = world @ inverse
    joints, weights = skin_attributes(obj.vertices, len(skeleton))
    points = np.column_stack((position.astype(np.float64), np.ones(len(position))))
    out = np.zeros_like(points)
    for slot in range(4):
        out += np.einsum("nij,nj->ni", palette[joints[:, slot]], points) * (weights[:, slot] / 255.0)[:, None]
    baked = out[:, :3].astype(np.float32)
    painted = [obj.indices[e.ib0:e.ib1] for e in getattr(obj, "doc", None).elements if e.skin_index < 0] \
        if getattr(obj, "doc", None) is not None else []
    if painted:
        static = np.unique(np.concatenate(painted))
        baked[static] = position[static]
    return baked


def read_materials(xdb_text: str) -> list[dict]:
    """Une entrée par primitive exportée, dans l'ordre du fichier : nom d'élément, mode de
    mélange (`alpha`/`add`) et drapeau `transparent` du xdb.

    Le glTF ne garde de ces drapeaux qu'un `alphaMode` que le lecteur générique écrase en
    « tout en mélange alpha ». Or le client ne mélange **que** les matériaux `transparent` :
    les autres (fûts de la tour, sabres, bielles, écorces, coque du navire, coupole `Back6`)
    sont peints sans mélange, avec un test d'alpha sur la texture et le tampon de profondeur ;
    leur alpha de sommet est sans effet. Même filtre que l'exportateur : éléments visibles
    d'au moins un triangle.
    """
    from tools.extract_menu_scene import parse_geometry_xdb
    out = []
    for element in parse_geometry_xdb(xdb_text).elements:
        if not element.material.visible or element.ib1 - element.ib0 < 3:
            continue
        out.append({"element": element.name,
                    "blend": "add" if element.material.blend == "BLEND_EFFECT_ADD" else "alpha",
                    "transparent": bool(element.material.transparent)})
    return out


def after_export(target: Path, meta: dict, source, server_root: Path) -> None:
    """Relève dans `scene.json` l'ordre de peinture (`sortMode OFFSETS` : l'ordre du fichier,
    comme en 4.0) et les drapeaux de matériau par primitive (voir `read_materials`)."""
    directory = Path(server_root) / "World" / "MainMenu" / DIRECTORY
    materials: dict[str, list[dict]] = {}
    for name in GEOMETRIES:
        path = directory / f"{name}.(Geometry).xdb"
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        if name == DIRECTORY:
            mode = read_sort_mode(text)
            if mode:
                meta["sortMode"] = mode
        materials[name] = read_materials(text)
    if materials:
        meta["materials"] = materials


HOOKS = SceneHooks(material=material, positions=positions, after_export=after_export)
