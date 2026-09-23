import { useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import type { StatsResponse } from '@/analytics/api';
import { bucketLabel, formatCount, niceTicks, timeTicks } from './format';
import s from './StatsScreen.module.css';

type Props = {
  series: StatsResponse['series'];
  bucket: StatsResponse['bucket'];
  /** Hauteur minimale : le graphique occupe ensuite toute la hauteur de son panneau. */
  minHeight: number;
};

const M = { top: 14, right: 14, bottom: 28, left: 46 };

/** Largeur du conteneur, suivie au redimensionnement. */
function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setSize({ width: el.clientWidth, height: el.clientHeight });
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([e]) => setSize({ width: Math.round(e.contentRect.width), height: Math.round(e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

/**
 * Aires des visiteurs (ambre, devant) et des pages vues (sarcelle, derrière) sur un seul
 * axe : deux comptes de même unité. Réticule et infobulle au survol, flèches au clavier.
 */
export function TrafficChart({ series, bucket, minHeight }: Props) {
  const [ref, size] = useSize<HTMLDivElement>();
  const width = size.width;
  const height = Math.max(minHeight, size.height);
  const [hover, setHover] = useState<number | null>(null);
  const n = series.length;
  const innerW = Math.max(0, width - M.left - M.right);
  const innerH = height - M.top - M.bottom;
  const max = Math.max(1, ...series.map(p => Math.max(p.views, p.visitors)));
  const yTicks = niceTicks(max, height < 220 ? 3 : 4);
  const yMax = yTicks[yTicks.length - 1];
  const x = (i: number) => M.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => M.top + innerH - (v / yMax) * innerH;
  const xTicks = timeTicks(series, bucket, Math.floor(innerW / 78));
  const withYear = n > 0 && new Date(series[0].t).getFullYear() !== new Date(series[n - 1].t).getFullYear();

  const line = (key: 'views' | 'visitors') => series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join('');
  const area = (key: 'views' | 'visitors') =>
    n ? `${line(key)}L${x(n - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z` : '';

  const indexAt = (clientX: number, el: Element) => {
    const r = el.getBoundingClientRect();
    const px = clientX - r.left;
    if (n <= 1) return 0;
    return Math.min(n - 1, Math.max(0, Math.round(((px - M.left) / innerW) * (n - 1))));
  };
  const onMove = (e: PointerEvent<SVGSVGElement>) => setHover(indexAt(e.clientX, e.currentTarget));
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!n) return;
    const stepBy = (d: number) => { e.preventDefault(); setHover(h => Math.min(n - 1, Math.max(0, (h ?? n - 1) + d))); };
    if (e.key === 'ArrowRight') stepBy(1);
    else if (e.key === 'ArrowLeft') stepBy(-1);
    else if (e.key === 'Home') { e.preventDefault(); setHover(0); }
    else if (e.key === 'End') { e.preventDefault(); setHover(n - 1); }
    else if (e.key === 'Escape') setHover(null);
  };

  const hp = hover !== null ? series[hover] : null;
  const tipLeft = hover !== null ? x(hover) : 0;
  const flip = tipLeft > width - 200;

  return (
    <div ref={ref} className={s.chart} style={{ minHeight }}>
      {width > 0 && (
        <svg
          width={width} height={height} className={s.chartSvg} tabIndex={0} role="img"
          aria-label="Visiteurs et pages vues par tranche ; flèches gauche et droite pour parcourir les valeurs"
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} onKeyDown={onKey}
          onFocus={() => setHover(h => h ?? (n ? n - 1 : null))} onBlur={() => setHover(null)}
        >
          {yTicks.map(v => (
            <g key={v}>
              <line x1={M.left} x2={width - M.right} y1={y(v)} y2={y(v)} className={v === 0 ? s.axis : s.grid} />
              <text x={M.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className={s.tick}>{formatCount(v)}</text>
            </g>
          ))}
          {xTicks.map(t => (
            <text key={t.index} x={x(t.index)} y={height - 8} textAnchor={t.index === 0 ? 'start' : t.index === n - 1 ? 'end' : 'middle'} className={s.tick}>
              {t.label}
            </text>
          ))}
          <path d={area('views')} className={s.areaViews} />
          <path d={line('views')} className={s.lineViews} />
          <path d={area('visitors')} className={s.areaVisitors} />
          <path d={line('visitors')} className={s.lineVisitors} />
          {hp && hover !== null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + innerH} className={s.crosshair} />
              <circle cx={x(hover)} cy={y(hp.views)} r={4.5} className={s.dotViews} />
              <circle cx={x(hover)} cy={y(hp.visitors)} r={4.5} className={s.dotVisitors} />
            </g>
          )}
        </svg>
      )}
      {hp && (
        <div className={s.tooltip} style={{ left: tipLeft, top: M.top, transform: flip ? 'translateX(calc(-100% - 14px))' : 'translateX(14px)' }} aria-hidden="true">
          <div className={s.tooltipDate}>{bucketLabel(hp.t, bucket, withYear)}</div>
          <div className={s.tooltipRow}><span className={`${s.key} ${s.keyVisitors}`} /><strong>{formatCount(hp.visitors)}</strong> visiteurs</div>
          <div className={s.tooltipRow}><span className={`${s.key} ${s.keyViews}`} /><strong>{formatCount(hp.views)}</strong> pages vues</div>
        </div>
      )}
    </div>
  );
}

/** Tableau des données du graphique, replié par défaut (lecture sans survol). */
export function TrafficTable({ series, bucket }: Omit<Props, 'minHeight'>) {
  return (
    <details className={s.dataTable}>
      <summary>Voir les données en tableau</summary>
      <div className={s.dataTableScroll}>
        <table>
          <thead><tr><th scope="col">{bucket === 'hour' ? 'Heure' : 'Jour'}</th><th scope="col">Visiteurs</th><th scope="col">Pages vues</th></tr></thead>
          <tbody>
            {[...series].reverse().map(p => (
              <tr key={p.t}><th scope="row">{bucketLabel(p.t, bucket, true)}</th><td>{formatCount(p.visitors)}</td><td>{formatCount(p.views)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
