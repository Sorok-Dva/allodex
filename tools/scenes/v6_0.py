"""6.0 « Broken Chains » : vallée du laboratoire et son manatrain suspendu.

La scène tient dans un seul maillage skinné (`Animated_Background_6_0`, 46 éléments) et
son animation `idle` de 3 000 images (100 s à 30 fps) : drapeau du laboratoire, arbres et
balancement du train sont natifs et passent par le mixeur du lecteur. Le VisObjectTemplate
n'attache aucun objet d'effet ; les 46 matériaux arment tous le défilement UV (`scrollRGB`)
mais le xdb n'en donne **aucune vitesse**, exactement comme en 4.0. Les binaires sont
identiques octet pour octet dans les clients 6.0, 7.0 et 8.0 archivés.

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

**Ce que le blob d'animation dit exactement — et ce qu'il ne dit pas.** Le blob a été
relu champ par champ (22 nœuds, 332 484 octets) pour lever un doute : le manatrain
parcourt-il son câble ? Non, et les données le disent de trois façons indépendantes.

* *La table de descripteurs est lue au bon endroit.* Entête : `u16 fps, u16 nb_images`,
  puis un pointeur auto-relatif vers les descripteurs en **4** et trois couples
  `(count, ptr)` en 8/12 (noms), 16/20 (ordre d'évaluation) et 24/28 (une quatrième table,
  posée juste après les descripteurs, que le décodage n'utilise pas). Un descripteur fait
  20 octets : `u16 drapeaux, u16 nb_canaux` puis **`ptr_courbes` en 4, `nb_valeurs` en 8,
  `ptr_flottants` en 12, `nb_flottants` en 16** — les deux champs pointeurs encadrent donc
  les deux compteurs, ce qui se lit mal à l'œil. Les 22 `ptr_flottants` tombent exactement
  sur `adresse_du_nom + longueur arrondie à 4 octets`, et les 22 `ptr_courbes` sur
  `ptr_flottants + 4 × nb_flottants` : le découpage par le nom que fait
  `parse_skeletal_animation` est celui des pointeurs du fichier, sans décalage.
* *La piste `Train` n'a qu'un seul canal.* Drapeau `0b1011111` (bit levé = composante
  fixe) : translation fixe à (0, 0, 0), échelle fixe à 1, angles Z et X fixes à 0, seul
  l'angle Y est animé — 3 001 entiers 16 bits dans [−165, +182], soit [−1,81°, +2,00°]
  avec une douzaine d'allers-retours sur les 100 s (période ≈ 16,7 s). Son parent
  `group1` (le porte-train, posé en (−36,1 ; −22,0 ; 9,44), échelle 0,81) est entièrement
  fixe. Le train **oscille au bout de son câble, il ne se déplace pas**.
* *L'`aabb` du xdb d'animation n'est pas une trajectoire balayée, c'est la boîte des
  trois éléments skinnés.* Centre (−32,9253 ; 17,8933 ; −0,618), extents (5,756 ; 44,863 ;
  22,954), soit la boîte [−38,68 ; −27,17] × [−26,97 ; 62,76] × [−23,57 ; 22,34]. Recalculée
  avec la formule du jeu (palette = `W_anim · inverse_stockée`) sur les 3 001 images et les
  seuls sommets `skinIndex` ≥ 0, elle vaut [−38,659 ; −27,1694] × [−26,9695 ; 62,511] ×
  [−23,5719 ; 22,3359] : **quatre faces sur six à 3·10⁻⁴ près** (X max et Z min viennent des
  arbres, Y min du train, Z max du drapeau), X min court de 0,02 et Y max de 0,25. Les
  90 unités en Y sont l'écart entre le train (Y ≈ −22) et les arbres (Y ≈ 25 à 62), pas un
  trajet. Et `aabbLastFrame` ne diffère de `aabb` que de 0,13 unité au plus : sur une
  animation bouclée, un train qui parcourrait le câble ferait diverger les deux boîtes de
  plusieurs dizaines d'unités.
* *Les arbres translatent, ils ne tournent pas.* `Bush_joint9`, `Tree01_joint3/4` et
  `Tree02_joint6/7` n'animent que Ty (et Tz pour trois d'entre eux), avec des u16 qui
  couvrent bien toute la plage 0…65535 — l'amplitude lue est donc l'amplitude stockée :
  0,017 à 0,284 unité selon l'articulation. Leurs trois angles sont fixes à 0 et leur
  rotation de bind est l'identité. Le feuillage bouge donc de quelques dixièmes d'unité,
  ce que confirme l'écart de 0,13 unité entre `aabb` et `aabbLastFrame`. Rien dans les
  données ne demande davantage.

Rien d'autre n'existe pour cette version : les paks 6.0 des clients archivés ne contiennent
que les textures, `Animated_Background_6_0.(Geometry).bin` et son `(SkeletalAnimation).bin`
(`Bird` et `Manatrain_6_0_01_FX` sont des textures que rien ne référence), et le
VisObjectTemplate n'a qu'un seul état, cette animation-là.

Le pendant de ce constat est côté lecteur : les 46 matériaux déclarent tous `scrollRGB`
sans aucune vitesse, comme en 4.0, et c'est `src/components/scene/MenuScene/v6/v6Clouds.ts`
qui fait dériver nuages, brume et rayons avec des vitesses **empruntées à la 7.0**.
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
