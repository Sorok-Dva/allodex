import { useEffect, useRef, useState } from 'react';
import type { LiveSnapshot } from '@/analytics/api';
import type { LiveStatus } from './client';
import { formatCount, pathLabel } from './format';
import s from './StatsScreen.module.css';

/** Nombre de lignes réservées : la hauteur du panneau ne bouge jamais. */
export const LIVE_SLOTS = 8;
const ROW_H = 38;
/** Durée du fondu de sortie d'une page qui quitte le classement. */
const LEAVE_MS = 450;
/** Historique du total pour la petite courbe (3 min à un instantané toutes les 2 s). */
const HISTORY = 90;

type Row = { path: string; visitors: number; rank: number; leaving: boolean };

type Props = {
  snapshot: LiveSnapshot | null;
  status: LiveStatus;
  activePath: string | null;
  onSelect: (path: string) => void;
};

/** Pages quittant le classement : gardées à leur place le temps du fondu. */
function useRows(snapshot: LiveSnapshot | null) {
  const [rows, setRows] = useState<Row[]>([]);
  const current = useRef<Row[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  useEffect(() => {
    if (!snapshot) return;
    const commit = (r: Row[]) => { current.current = r; setRows(r); };
    const top = snapshot.pages.filter(p => p.visitors > 0).slice(0, LIVE_SLOTS);
    const next = new Map(top.map((p, rank) => [p.path, { path: p.path, visitors: p.visitors, rank, leaving: false }]));
    const out: Row[] = [...next.values()];
    for (const r of current.current) {
      if (next.has(r.path)) {
        const t = timers.current.get(r.path);
        if (t) { clearTimeout(t); timers.current.delete(r.path); }
        continue;
      }
      if (r.leaving) { out.push(r); continue; }
      out.push({ ...r, leaving: true });
      timers.current.set(r.path, setTimeout(() => {
        timers.current.delete(r.path);
        commit(current.current.filter(c => !(c.path === r.path && c.leaving)));
      }, LEAVE_MS));
    }
    commit(out);
  }, [snapshot]);
  useEffect(() => () => { for (const t of timers.current.values()) clearTimeout(t); }, []);
  return rows;
}

function useHistory(snapshot: LiveSnapshot | null) {
  const [history, setHistory] = useState<number[]>([]);
  useEffect(() => {
    if (snapshot) setHistory(h => [...h, snapshot.total].slice(-HISTORY));
  }, [snapshot]);
  return history;
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  const w = 200;
  const h = 40;
  // Échelle fixe sur l'historique complet : la courbe naît à droite et défile vers la gauche.
  const pts = values.map((v, i) => `${(((i + HISTORY - values.length) / (HISTORY - 1)) * w).toFixed(1)},${(h - 2 - (v / max) * (h - 6)).toFixed(1)}`);
  return (
    <div className={s.sparkBox}>
      <svg className={s.spark} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" x2={w} y1={h - 1} y2={h - 1} className={s.axis} vectorEffect="non-scaling-stroke" />
        {values.length > 1 && <polyline points={pts.join(' ')} className={s.sparkLine} vectorEffect="non-scaling-stroke" />}
      </svg>
      <span className={s.sparkCaption}>3 dernières minutes</span>
    </div>
  );
}

const STATUS_TEXT: Record<LiveStatus, string> = {
  connecting: 'Connexion au direct…',
  open: 'Mis à jour toutes les 2 secondes',
  reconnecting: 'Direct interrompu, reconnexion…',
};

export function LivePanel({ snapshot, status, activePath, onSelect }: Props) {
  const rows = useRows(snapshot);
  const history = useHistory(snapshot);
  const max = Math.max(1, ...rows.filter(r => !r.leaving).map(r => r.visitors));
  const hidden = snapshot ? snapshot.pages.filter(p => p.visitors > 0).slice(LIVE_SLOTS) : [];
  const hiddenVisitors = hidden.reduce((a, p) => a + p.visitors, 0);

  return (
    <section className={`${s.panel} ${s.live}`} aria-labelledby="live-title">
      <header className={s.panelHead}>
        <h2 id="live-title" className={s.panelTitle}>En direct</h2>
        <span className={`${s.liveState} ${status === 'open' ? '' : s.liveStateOff}`}>{STATUS_TEXT[status]}</span>
      </header>
      <div className={s.liveHero}>
        <div>
          <div className={s.liveTotal} aria-live="polite" aria-atomic="true">
            <span key={snapshot?.total ?? -1} className={s.bump}>{snapshot ? formatCount(snapshot.total) : '—'}</span>
          </div>
          <div className={s.liveCaption}>{snapshot?.total === 1 ? 'visiteur sur le site' : 'visiteurs sur le site'}</div>
        </div>
        <Sparkline values={history} />
      </div>
      <ol className={s.liveList} style={{ height: LIVE_SLOTS * ROW_H }} aria-label="Pages consultées en ce moment">
        {rows.length === 0 && <li className={s.liveEmpty}>{snapshot ? 'Personne sur le site en ce moment.' : 'En attente du premier instantané…'}</li>}
        {rows.map(r => {
          const { label, detail } = pathLabel(r.path);
          return (
            <li
              key={r.path}
              className={`${s.liveRow} ${r.leaving ? s.liveRowLeaving : ''} ${activePath === r.path ? s.rowActive : ''}`}
              style={{ transform: `translateY(${r.rank * ROW_H}px)`, height: ROW_H }}
              aria-hidden={r.leaving || undefined}
            >
              <button type="button" className={s.liveButton} onClick={() => onSelect(r.path)} tabIndex={r.leaving ? -1 : 0}
                title={`Filtrer le tableau sur ${r.path}`}>
                <span className={s.rowText}>
                  <span className={s.rowLabel}>{label}</span>
                  {detail && <span className={s.rowDetail}>{detail}</span>}
                </span>
                <span className={s.liveCount}><span key={r.visitors} className={s.bump}>{formatCount(r.visitors)}</span></span>
                <span className={s.barTrack} aria-hidden="true">
                  <span className={`${s.bar} ${s.barVisitors}`} style={{ transform: `scaleX(${r.leaving ? 0 : r.visitors / max})` }} />
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className={s.liveMore}>
        {hidden.length > 0 ? `et ${hidden.length} autre${hidden.length > 1 ? 's' : ''} page${hidden.length > 1 ? 's' : ''} (${formatCount(hiddenVisitors)} visiteur${hiddenVisitors > 1 ? 's' : ''})` : ' '}
      </p>
    </section>
  );
}
