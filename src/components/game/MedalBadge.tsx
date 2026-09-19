import type { CSSProperties } from 'react';
import { T, tex } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import { frameSuffix, medalTier, type MedalTier } from '@/data/medals.logic';
import { toRoman } from '@/lib/roman';
import s from './MedalBadge.module.css';

/**
 * Le jeu dessine le badge d'un seul tenant : la texture `MedalFrame[Complete][30|50|100|500]`
 * porte à la fois la plaque de l'icône et l'écu du score, puis l'icône, l'étiquette de palier
 * et le score sont posés par-dessus.
 *
 * Échelle relevée sur `refs/astral.png` : la plaque de 60 × 60 px de `MedalFrame` occupe
 * 53 × 52 px à l'écran (x 847,5→900,5 ; y 327→379) et celle de 55 × 55 px de `MedalFrame30`
 * en occupe 48 (x 851→899), soit **0,875** dans les deux cas. Le centre de la plaque tombe
 * toujours au même endroit du parchemin : (38,5 ; 37,5) depuis son coin haut-gauche
 * (centres d'icônes mesurés : entrée 2 → (39 ; 37), entrée 3 → (39,5 ; 38)).
 */
const SCALE = 0.875;
const ANCHOR_X = 38.5;
const ANCHOR_Y = 37.5;
/** Icône mesurée à 41 px de contenu coloré, bordure sombre comprise → 42 px dessinés. */
const ICON = 42;

/**
 * Centre de la plaque (le logement de l'icône) en pixels de texture, **identique pour les
 * cinq paliers** : les cinq textures `MedalFrame*` portent la même plaque aux mêmes
 * coordonnées, seul l'ornement qui l'entoure grandit (vérifié en itération 2b : sur
 * `MedalFrameComplete`, `…30`, `…50`, `…100` et `…500`, la région y 20→70 / x 25→76 est
 * identique au pixel près, écart moyen 0,2/255). C'est pourquoi le cadre, l'icône et
 * l'écu restent alignés quel que soit le palier.
 */
const PLATE_X = 50.5;
const PLATE_Y = 44.5;

/** Ligne de base du score dans l'écu, en pixels de texture, et taille de la texture. */
type TierGeom = { w: number; h: number; scoreY: number };

/**
 * Géométrie de chaque palier ; le **nom** de la texture vient de `frameSuffix`, seule source
 * de vérité du seuil (voir `medals.logic.ts`), pour que le cadre affiché et le chiffre romain
 * ne puissent pas diverger.
 *
 * `scoreY` est relevé sur les captures, en centre de glyphes relatif au haut du parchemin :
 * palier I « 20 » (`refs/astral.png`, parchemin y 315, glyphes y 381→391, centre +71) ;
 * palier II « 30 » (parchemin y 426, glyphes y 491→501, centre +70) ; palier IV « 100 »
 * (`refs/equip.png`, entrée « Divin », parchemin y 366, glyphes y 431→441, centre +70).
 * L'écu tombe donc toujours à la même hauteur à l'écran quel que soit le palier : les
 * paliers III et V, absents des captures, sont extrapolés sur ce même centre +70.
 */
const TIERS: Record<MedalTier, TierGeom> = {
  1: { w: 81, h: 109, scoreY: 88 },
  2: { w: 90, h: 113, scoreY: 87 },
  3: { w: 94, h: 120, scoreY: 86.9 },
  4: { w: 98, h: 121, scoreY: 86.3 },
  5: { w: 100, h: 129, scoreY: 86.9 },
};

export function MedalBadge({ score, icon, complete }: { score: number; icon: string; complete: boolean }) {
  const tier = medalTier(score);
  const g = TIERS[tier];
  const frame = `${T.medals}/MedalFrame${complete ? 'Complete' : ''}${frameSuffix(score)}`;
  const iconLeft = PLATE_X * SCALE - ICON / 2;
  const iconTop = PLATE_Y * SCALE - ICON / 2;

  const tagStyle: CSSProperties = {
    ...nineSlice('rank-tag', [2, 2, 2, 2], { fill: true }),
    right: g.w * SCALE - (iconLeft + ICON) + 2,
    top: iconTop + ICON - 3 - 11,
  };

  return (
    <div
      className={s.badge}
      style={{
        left: ANCHOR_X - PLATE_X * SCALE,
        top: ANCHOR_Y - PLATE_Y * SCALE,
        width: g.w * SCALE,
        height: g.h * SCALE,
        backgroundImage: `url(${tex(frame)})`,
      }}
    >
      <img className={s.icon} style={{ left: iconLeft, top: iconTop }} src={tex(icon)} alt="" draggable={false} />
      <span className={s.tag} style={tagStyle}>{toRoman(tier)}</span>
      {/* L'écu est centré sur la plaque, pas sur la texture (qui déborde à droite au
          palier I et des deux côtés aux paliers suivants) : le score suit la plaque. */}
      <span className={s.score} style={{ left: PLATE_X * SCALE, top: g.scoreY * SCALE - 10.5 }}>{score}</span>
    </div>
  );
}
