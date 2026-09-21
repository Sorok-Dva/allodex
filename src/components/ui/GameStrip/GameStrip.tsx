import type { CSSProperties } from 'react';
import { sprite } from '@/lib/assets';
import s from './GameStrip.module.css';

type Props = {
  /** Préfixe des sprites : « band » → `band-left`, `band-mid`, `band-right`. */
  base: string;
  /** Largeur des deux extrémités ornées, en pixels (jamais mise à l'échelle). */
  cap: number;
  className?: string;
  style?: CSSProperties;
};

/**
 * Bande horizontale du jeu composée de trois morceaux : extrémité gauche, tranche
 * centrale répétée (`repeat-x`, 8 px de large) et extrémité droite. Se superpose au
 * parent (position absolue) pour servir de fond à une pilule, une plaque ou un bandeau.
 */
export function GameStrip({ base, cap, className, style }: Props) {
  return (
    <span className={`${s.strip} ${className ?? ''}`} style={style} aria-hidden="true">
      <span className={s.mid} style={{ left: cap, right: cap, backgroundImage: `url(${sprite(`${base}-mid`)})` }} />
      <span className={s.cap} style={{ left: 0, width: cap, backgroundImage: `url(${sprite(`${base}-left`)})` }} />
      <span className={s.cap} style={{ right: 0, width: cap, backgroundImage: `url(${sprite(`${base}-right`)})` }} />
    </span>
  );
}
