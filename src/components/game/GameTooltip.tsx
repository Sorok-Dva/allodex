import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { nineSlice } from '@/lib/nineSlice';
import s from './GameTooltip.module.css';

const MARGIN = 8;
const GAP = 8;
/**
 * Décalage de l'infobulle par rapport au curseur, relevé sur `refs/tooltip.png` :
 * l'infobulle de « Connecté avec les étoiles » a son coin haut-gauche en (899, 331)
 * alors que le pointeur était sur le badge de l'entrée, soit +9 px à droite et +11 px
 * sous le curseur. C'est la pose de l'infobulle du jeu (`align="cursor"`).
 */
const CURSOR_DX = 9;
const CURSOR_DY = 11;

type Props = {
  /** Boîte d'ancrage en coordonnées viewport ; un rectangle de taille nulle = le curseur. */
  anchor: DOMRect | null;
  title?: string;
  /** Deuxième ligne du jeu : « Date : HH:MM JJ.MM.AAAA ». */
  date?: string;
  hint?: string;
  /**
   * `center` (défaut) : centrée sous l'ancre, comme la barre d'actions de l'accueil.
   * `cursor` : coin haut-gauche à `anchor` + (9, 11), comme le panneau Succès du jeu.
   */
  align?: 'center' | 'cursor';
  children?: ReactNode;
  className?: string;
};

export function GameTooltip({ anchor, title, date, hint, align = 'center', children, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<CSSProperties>({ visibility: 'hidden' });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!anchor || !el) { setPos({ visibility: 'hidden' }); return; }
    const rect = el.getBoundingClientRect();
    const cursor = align === 'cursor';

    let top = cursor ? anchor.bottom + CURSOR_DY : anchor.bottom + GAP;
    if (top + rect.height + MARGIN > window.innerHeight) top = anchor.top - rect.height - (cursor ? CURSOR_DY : GAP);
    top = Math.min(Math.max(top, MARGIN), Math.max(MARGIN, window.innerHeight - rect.height - MARGIN));

    let left = cursor ? anchor.left + CURSOR_DX : anchor.left + anchor.width / 2 - rect.width / 2;
    left = Math.min(Math.max(left, MARGIN), Math.max(MARGIN, window.innerWidth - rect.width - MARGIN));

    setPos({ top, left, visibility: 'visible' });
  }, [anchor, title, date, hint, children, align]);

  if (!anchor) return null;

  // Sans `fill` : l'intérieur opaque du sprite n'est pas dessiné, le fond translucide
  // du CSS reste visible.
  const frameStyle: CSSProperties = { ...nineSlice('tooltip-frame', [4, 4, 4, 4]), ...pos };

  return (
    <div ref={ref} className={`${s.tooltip} ${className ?? ''}`} style={frameStyle}>
      {title && <div className={s.title}>{title}</div>}
      {date && <div className={s.date}>{date}</div>}
      {children && <div className={s.body}>{children}</div>}
      {hint && (
        <>
          <div className={s.sep} />
          <div className={s.hint}>{hint}</div>
        </>
      )}
    </div>
  );
}
