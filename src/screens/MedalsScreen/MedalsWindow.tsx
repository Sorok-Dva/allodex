import type { ReactNode } from 'react';
import { T, sprite, tex } from '@/lib/assets';
import { GameStrip } from '@/components/game/GameStrip';
import { GameFilters } from '@/components/game/GameFilters';
import s from './MedalsWindow.module.css';

type Props = {
  title: string;
  points: number;
  onClose: () => void;
  nav: ReactNode;
  content: ReactNode;
};

/**
 * Chrome de la fenêtre « Succès » à l'échelle 1:1 (886 × 592), relevé au pixel sur
 * `refs/astral.png` (écran 1920 × 1009, fenêtre x 518→1404, y 191→783). Toutes les
 * constantes CSS sont exprimées dans le repère local de la fenêtre, c'est-à-dire en
 * pixels écran moins l'origine (518, 191).
 *
 * La plaque de titre flotte au-dessus du décor du jeu : au-dessus du bandeau turquoise
 * et en dehors de la plaque, on voit la scène, pas la fenêtre — d'où l'absence de fond
 * sur la bande y 0→31.
 */
export function MedalsWindow({ title, points, onClose, nav, content }: Props) {
  return (
    <div className={s.window}>
      <GameFilters />

      {/* Fond de la colonne de navigation : texture du client, placée par recalage
          linéaire sur la capture (tex y 64 ↔ écran 260, tex y 598 ↔ écran 759). */}
      <div className={s.navBack} style={{ backgroundImage: `url(${tex(`${T.medals}/FrameNavigation`)})` }} />

      <div className={s.plate}>
        <GameStrip base="title-plate" cap={38} />
        <span className={s.title}>{title}</span>
      </div>

      <div className={s.band}>
        <GameStrip base="band" cap={112} />
        {/* Le jeu n'insère pas d'espace avant « points ». */}
        <span className={s.points}>{String(points)}points de succès</span>
      </div>

      <div className={s.railTop} style={{ backgroundImage: `url(${sprite('rail-top')})` }} />
      <div className={s.railBottom} style={{ backgroundImage: `url(${sprite('rail-bottom')})` }} />
      <div className={s.railRight} style={{ backgroundImage: `url(${sprite('rail-right')})` }} />
      <div className={`${s.corner} ${s.cornerTl}`} style={{ backgroundImage: `url(${sprite('corner-tl')})` }} />
      <div className={`${s.corner} ${s.cornerTr}`} style={{ backgroundImage: `url(${sprite('corner-tr')})` }} />
      <div className={`${s.corner} ${s.cornerBl}`} style={{ backgroundImage: `url(${sprite('corner-bl')})` }} />
      <div className={`${s.corner} ${s.cornerBr}`} style={{ backgroundImage: `url(${sprite('corner-br')})` }} />

      <div className={s.navSlot}>{nav}</div>
      <div className={s.contentSlot}>{content}</div>

      <div className={s.divider} style={{ backgroundImage: `url(${sprite('divider-v')})` }} />

      {/* Les textures `Cross/Close*` extraites du client sont des aplats rouges
          inutilisables ; le bouton du jeu (plaque olive, anneau or, disque orange,
          croix sombre) est reconstitué en CSS à partir des couleurs relevées. */}
      <button type="button" className={s.close} onClick={onClose} aria-label="Fermer" title="Fermer">
        <span className={s.closeDisc}><span className={s.closeCross} /></span>
      </button>
    </div>
  );
}
