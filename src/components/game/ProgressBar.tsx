import type { CSSProperties } from 'react';
import { T, tex } from '@/lib/assets';
import s from './ProgressBar.module.css';

/** Pointes des textures `ProgressBar` (154 × 13) et `ProgressBarGauge` (146 × 9). */
const CAP = 8;

type Props = {
  value: number;
  max: number;
  label?: string;
  className?: string;
  style?: CSSProperties;
};

const nineSlice = (texture: string): CSSProperties => ({
  borderImageSource: `url(${tex(`${T.medals}/${texture}`)})`,
  borderImageSlice: `0 ${CAP} 0 ${CAP} fill`,
  borderImageWidth: `0 ${CAP}px 0 ${CAP}px`,
  borderWidth: `0 ${CAP}px`,
});

/**
 * Barre de progression du jeu : les textures `ProgressBar` (piste) et `ProgressBarGauge`
 * (jauge) sont étirées en 9 tranches horizontalement, hauteur native 13 px, pointes de
 * 8 px conservées. Relevé sur `refs/astral.png` : barre x 925→1312 (388 px), y 387→399,
 * et une barre pleine est **uniformément** brune, pointes comprises : la jauge couvre
 * toute la piste, elle n'est pas rentrée de 4 px comme la différence de largeur des deux
 * textures le laisserait croire.
 */
export function ProgressBar({ value, max, label, className, style }: Props) {
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;

  return (
    <div className={`${s.bar} ${className ?? ''}`} style={style}>
      <span className={s.track} style={nineSlice('ProgressBar')} aria-hidden="true" />
      <span className={s.gauge} style={{ ...nineSlice('ProgressBarGauge'), width: `${pct * 100}%` }} aria-hidden="true" />
      <span className={s.text}>{label ?? `${value.toLocaleString('fr-FR')} sur ${max.toLocaleString('fr-FR')}`}</span>
    </div>
  );
}
