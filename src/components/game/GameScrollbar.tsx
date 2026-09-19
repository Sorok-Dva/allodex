import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';
import { sprite } from '@/lib/assets';
import s from './GameScrollbar.module.css';

/** Hauteur des sprites `scroll-up` / `scroll-down`. */
const ARROW = 23;
/**
 * Hauteur du curseur, fixe comme dans le jeu (20 px, relevé sur `refs/astral.png` et
 * `refs/navscroll.png`) : c'est la valeur par défaut des deux ascenseurs du site.
 */
const THUMB = 20;
/** Hauteur minimale du curseur proportionnel (`thumbSize={null}`). */
const MIN_THUMB = 18;
/** Défilement d'un clic sur une flèche (px). */
const STEP = 40;

type Metrics = { top: number; scroll: number; client: number };
const ZERO: Metrics = { top: 0, scroll: 0, client: 0 };

type Props = {
  /** Conteneur défilant piloté par l'ascenseur. */
  targetRef: RefObject<HTMLElement | null>;
  /**
   * Hauteur fixe du curseur, en pixels ; 20 px par défaut, comme le jeu. `null`
   * rétablit un curseur proportionnel au contenu, avec un minimum de 18 px.
   */
  thumbSize?: number | null;
  /** Pas des flèches, 40 px par défaut. */
  step?: number;
  className?: string;
  style?: CSSProperties;
};

export function GameScrollbar({ targetRef, thumbSize = THUMB, step = STEP, className, style }: Props) {
  const [m, setMetrics] = useState<Metrics>(ZERO);
  const trackRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; top: number } | null>(null);

  const read = useCallback(() => {
    const el = targetRef.current;
    if (!el) return;
    setMetrics(prev =>
      prev.top === el.scrollTop && prev.scroll === el.scrollHeight && prev.client === el.clientHeight
        ? prev
        : { top: el.scrollTop, scroll: el.scrollHeight, client: el.clientHeight },
    );
  }, [targetRef]);

  // Le contenu de la liste change à chaque dépliage : on relit les mesures après
  // chaque rendu du parent, en plus des événements de défilement et de redimensionnement.
  useLayoutEffect(read);

  useEffect(() => {
    const el = targetRef.current;
    if (!el) return;
    el.addEventListener('scroll', read, { passive: true });
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(read);
      ro.observe(el);
      if (el.firstElementChild) ro.observe(el.firstElementChild);
    }
    return () => { el.removeEventListener('scroll', read); ro?.disconnect(); };
  }, [targetRef, read]);

  const max = Math.max(0, m.scroll - m.client);
  const ratio = m.scroll > 0 ? Math.min(1, m.client / m.scroll) : 1;
  const progress = max > 0 ? Math.min(1, Math.max(0, m.top / max)) : 0;
  const canScroll = max > 0.5;

  const scrollBy = (delta: number) => {
    const el = targetRef.current;
    if (el) el.scrollTop = Math.min(max, Math.max(0, el.scrollTop + delta));
    read();
  };

  const onThumbDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = targetRef.current;
    if (!el) return;
    drag.current = { y: e.clientY, top: el.scrollTop };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onThumbMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = targetRef.current;
    const d = drag.current;
    if (!el || !d) return;
    const track = trackRef.current?.clientHeight ?? 0;
    const thumb = thumbSize ?? Math.max(MIN_THUMB, track * ratio);
    const travel = Math.max(1, track - thumb);
    el.scrollTop = Math.min(max, Math.max(0, d.top + ((e.clientY - d.y) / travel) * max));
    read();
  };
  const onThumbUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };

  const thumbStyle: CSSProperties = thumbSize
    ? { height: `${thumbSize}px`, top: `calc((100% - ${thumbSize}px) * ${progress})` }
    : { height: `${(ratio * 100).toFixed(3)}%`, top: `${(progress * (100 - ratio * 100)).toFixed(3)}%` };

  return (
    <div className={`${s.bar} ${className ?? ''}`} style={style}>
      <button
        type="button" className={`${s.arrow} ${s.up} ${m.top <= 0 ? s.off : ''}`} data-testid="scrollbar-up"
        aria-label="Défiler vers le haut" disabled={!canScroll || m.top <= 0}
        style={{ height: ARROW, backgroundImage: `url(${sprite('scroll-up')})` }}
        onClick={() => scrollBy(-step)}
      />
      <div
        ref={trackRef} className={s.track} data-testid="scrollbar-track"
        style={{ top: ARROW, bottom: ARROW, backgroundImage: `url(${sprite('scroll-track')})` }}
      >
        {canScroll && (
          <div
            className={s.thumb} data-testid="scrollbar-thumb" role="presentation"
            style={{ ...thumbStyle, backgroundImage: `url(${sprite('scroll-thumb')})` }}
            onPointerDown={onThumbDown} onPointerMove={onThumbMove} onPointerUp={onThumbUp} onPointerCancel={onThumbUp}
          />
        )}
      </div>
      <button
        type="button" className={`${s.arrow} ${s.down} ${m.top >= max ? s.off : ''}`} data-testid="scrollbar-down"
        aria-label="Défiler vers le bas" disabled={!canScroll || m.top >= max}
        style={{ height: ARROW, backgroundImage: `url(${sprite('scroll-down')})` }}
        onClick={() => scrollBy(step)}
      />
    </div>
  );
}
