import { useEffect, useRef, useState } from 'react';
import type { Range, TalentCounts, TalentStatsResponse } from '@/analytics/api';
import { UnauthorizedError, type StatsSource } from './client';
import { RANGE_LABELS, formatCount } from './format';
import { RankList, type RankRow } from './RankList';
import s from './StatsScreen.module.css';

const REFRESH_MS = 60_000;

const TILES: { key: keyof TalentCounts; label: string }[] = [
  { key: 'builds', label: 'Builds composés' },
  { key: 'generations', label: 'Générations' },
  { key: 'shares', label: 'Partages' },
  { key: 'views', label: 'Vues de builds' },
];

const classLabel = (version: string, cls: string) => `${cls.charAt(0).toUpperCase()}${cls.slice(1)} · ${version}`;

function buildUrl(b: { version: string; cls: string; b: string | null; b2: string | null }) {
  const q = new URLSearchParams({ v: b.version, c: b.cls });
  if (b.b) q.set('b', b.b);
  if (b.b2) q.set('b2', b.b2);
  return `/talents?${q}`;
}

/** Calculateur de talents : builds composés, partagés et ouverts depuis un lien (`/api/admin/talents`). */
export function TalentsPanel({ source, range, onUnauthorized }: { source: StatsSource; range: Range; onUnauthorized: () => void }) {
  const [data, setData] = useState<TalentStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const unauthorized = useRef(onUnauthorized);
  unauthorized.current = onUnauthorized;

  useEffect(() => {
    const ctrl = new AbortController();
    source.talents(range, ctrl.signal).then(
      d => { if (!ctrl.signal.aborted) { setData(d); setError(null); } },
      err => {
        if (ctrl.signal.aborted) return;
        if (err instanceof UnauthorizedError) { unauthorized.current(); return; }
        setError(err instanceof Error ? err.message : String(err));
      },
    );
    const id = setTimeout(() => setNonce(n => n + 1), REFRESH_MS);
    return () => { ctrl.abort(); clearTimeout(id); };
  }, [source, range, nonce]);

  const classes: RankRow[] = (data?.classes ?? []).map(c => ({
    key: `${c.version}/${c.cls}`, label: classLabel(c.version, c.cls), value: c.builds,
    extra: [formatCount(c.shares), formatCount(c.views)],
  }));
  const top: RankRow[] = (data?.top ?? []).map(b => ({
    key: b.id, label: classLabel(b.version, b.cls), detail: [b.b, b.b2].filter(Boolean).join(' + '), value: b.period.views,
    extra: [
      formatCount(b.period.shares),
      formatCount(b.total.views),
      <a key="open" href={buildUrl(b)} target="_blank" rel="noopener noreferrer" title="Ouvrir le build dans le calculateur">Ouvrir</a>,
    ],
  }));

  return (
    <section className={s.talentsSection} aria-labelledby="talents-title">
      <h2 id="talents-title" className={s.sectionTitle}>Calculateur de talents</h2>
      {error && <p className={s.banner} role="alert">Statistiques des builds indisponibles ({error}).</p>}
      {data && (
        <>
          <div className={s.talentTiles}>
            {TILES.map(t => (
              <div key={t.key} className={s.tile}>
                <div className={s.kpiLabel}>{t.label}</div>
                <div className={s.kpiValue}>{formatCount(data.totals[t.key])}</div>
                <div className={s.tileNote}>{formatCount(data.allTime[t.key])} depuis le début</div>
              </div>
            ))}
          </div>
          <div className={s.ranksRow}>
            <RankList title="Classes" metric="Builds" tone="visitors" rows={classes} format={formatCount}
              extraHeads={[{ label: 'Partages' }, { label: 'Vues' }]} empty={`Aucun build sur ${RANGE_LABELS[range].long}.`} />
            <RankList title="Builds les plus vus" metric="Vues" tone="views" rows={top} format={formatCount}
              extraHeads={[{ label: 'Partages', narrow: true }, { label: 'Total', narrow: true }, { label: '', width: '4.4em' }]}
              empty={`Aucun build vu sur ${RANGE_LABELS[range].long}.`} />
          </div>
        </>
      )}
    </section>
  );
}
