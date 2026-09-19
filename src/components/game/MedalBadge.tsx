import type { CSSProperties } from 'react';
import { T, sprite, spriteSize, tex } from '@/lib/assets';
import { medalTier, type MedalTier } from '@/data/medals.logic';
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

type TierGeom = {
  /** Suffixe de la texture. */ suffix: string;
  w: number; h: number;
  /** Centre de la plaque, en pixels de texture. */ cx: number; cy: number;
  /** Ligne de base du score, en pixels de texture. */ scoreY: number;
};

/**
 * Plaques relevées dans les textures : `MedalFrame` x 21→80 / y 15→74 ;
 * `MedalFrame30` et `MedalFrame50` x 23→77 / y 16→70. Les paliers IV et V n'apparaissent
 * dans aucune capture : leur centre et la ligne de base du score sont extrapolés.
 */
const TIERS: Record<MedalTier, TierGeom> = {
  1: { suffix: '', w: 81, h: 109, cx: 50.5, cy: 44.5, scoreY: 88.5 },
  2: { suffix: '30', w: 90, h: 113, cx: 50, cy: 43, scoreY: 86 },
  3: { suffix: '50', w: 94, h: 120, cx: 50, cy: 43, scoreY: 92 },
  4: { suffix: '100', w: 98, h: 121, cx: 50, cy: 38.5, scoreY: 88 },
  5: { suffix: '500', w: 100, h: 129, cx: 50, cy: 38.5, scoreY: 96 },
};

export function MedalBadge({ score, icon, complete }: { score: number; icon: string; complete: boolean }) {
  const tier = medalTier(score);
  const g = TIERS[tier];
  const frame = `${T.medals}/MedalFrame${complete ? 'Complete' : ''}${g.suffix}`;
  const iconLeft = g.cx * SCALE - ICON / 2;
  const iconTop = g.cy * SCALE - ICON / 2;

  const [tt, tr, tb, tl] = spriteSize('rank-tag')?.slice ?? [2, 2, 2, 2];
  const tagStyle: CSSProperties = {
    borderImageSource: `url(${sprite('rank-tag')})`,
    borderImageSlice: `${tt} ${tr} ${tb} ${tl} fill`,
    borderImageWidth: `${tt}px ${tr}px ${tb}px ${tl}px`,
    borderWidth: `${tt}px ${tr}px ${tb}px ${tl}px`,
    right: g.w * SCALE - (iconLeft + ICON) + 2,
    top: iconTop + ICON - 3 - 11,
  };

  return (
    <div
      className={s.badge}
      style={{
        left: ANCHOR_X - g.cx * SCALE,
        top: ANCHOR_Y - g.cy * SCALE,
        width: g.w * SCALE,
        height: g.h * SCALE,
        backgroundImage: `url(${tex(frame)})`,
      }}
    >
      <img className={s.icon} style={{ left: iconLeft, top: iconTop }} src={tex(icon)} alt="" draggable={false} />
      <span className={s.tag} style={tagStyle}>{toRoman(tier)}</span>
      <span className={s.score} style={{ top: g.scoreY * SCALE - 10.5 }}>{score}</span>
    </div>
  );
}
