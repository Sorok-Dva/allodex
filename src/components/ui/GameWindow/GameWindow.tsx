import { useState, type CSSProperties, type ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameWindow.module.css';

/**
 * Fenêtre du jeu bâtie sur celle de l'hôtel des ventes (`Interface/Ingame/ContextAuction`,
 * client 17.0), aux cotes de ses layouts xdb :
 *
 * - cadre `AuctionFrame` (`WidgetLayerTiledTexture` : LeftX 196, MiddleX 64 répété, RightX 193,
 *   TopY 790 — la hauteur ne s'étire pas), 857 × 790 par défaut ;
 * - plaque de titre `Contextructor/WindowHeader/TiledHeader` (LeftX 96, MiddleX 32, RightX 96),
 *   posée de x 64 à largeur − 64, y −14, hauteur 44 ; texte centré dans x 48 → −45, y 8, 22 px ;
 * - fermeture `Contextructor/CornerCross` : coin doré `GoldenCorner` 52 × 52 collé en haut à
 *   droite (1 px du bord), croix 32 × 32 à 1 px du haut et du bord droit, états Normal /
 *   Pressed et halo Highlight au survol.
 *
 * Les bandeaux du cadre (haut turquoise y 33 → 160, bas y 650 → 760) sont des zones du
 * dessin : `header`, `children` et `footer` s'y placent (voir le CSS).
 */
export const WINDOW_HEIGHT = 790;
export const WINDOW_MIN_WIDTH = 453;

const FRAME = 'Interface/Ingame/ContextAuction/AuctionFrame';
const PLATE = 'Interface/Ingame/Contextructor/WindowHeader/TiledHeader';
const CORNER = 'Interface/Ingame/Contextructor/CornerCross/GoldenCorner';
const CROSS = 'Interface/Ingame/Contextructor/CornerCross/CornerCross';

type Props = {
  title: string;
  onClose: () => void;
  closeLabel: string;
  width?: number;
  /** Contenu du bandeau turquoise du haut. */
  header?: ReactNode;
  /** Contenu du bandeau du bas. */
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
};

export function GameWindow({ title, onClose, closeLabel, width = 857, header, footer, children, className, style }: Props) {
  const [pressed, setPressed] = useState(false);
  const w = Math.max(WINDOW_MIN_WIDTH, width);
  return (
    <section className={`${s.window} ${className ?? ''}`} style={{ width: w, height: WINDOW_HEIGHT, ...style }} aria-label={title}>
      <span className={s.frame} aria-hidden="true" style={{ borderImageSource: `url(${tex(FRAME)})` }} />
      <div className={s.plate}>
        <span className={s.plateSkin} aria-hidden="true" style={{ borderImageSource: `url(${tex(PLATE)})` }} />
        <h1 className={s.title}>{title}</h1>
      </div>
      {header && <div className={s.header}>{header}</div>}
      <div className={s.body}>{children}</div>
      {footer && <div className={s.footer}>{footer}</div>}
      <div className={s.close}>
        <span className={s.corner} aria-hidden="true" style={{ backgroundImage: `url(${tex(CORNER)})` }} />
        <button type="button" className={s.cross} onClick={onClose} aria-label={closeLabel} title={closeLabel}
          onPointerDown={() => setPressed(true)} onPointerUp={() => setPressed(false)} onPointerLeave={() => setPressed(false)}
          style={{ backgroundImage: `url(${tex(`${CROSS}${pressed ? 'Pressed' : 'Normal'}`)})` }}>
          <span className={s.crossGlow} aria-hidden="true" style={{ backgroundImage: `url(${tex(`${CROSS}Highlight`)})` }} />
        </button>
      </div>
    </section>
  );
}
