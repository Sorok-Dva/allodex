import { useState, type CSSProperties, type ReactNode } from 'react';
import s from './StatsScreen.module.css';

export type RankRow = {
  key: string;
  label: string;
  detail?: string | null;
  /** Mesure principale : longueur de la barre, colonne en gras. */
  value: number;
  /** Colonnes secondaires, déjà formatées. */
  extra?: ReactNode[];
};

type Props = {
  title: string;
  /** Nom de la mesure principale (en-tête de colonne). */
  metric: string;
  tone: 'visitors' | 'views';
  rows: RankRow[];
  format: (n: number) => string;
  /** En-têtes des colonnes secondaires ; `narrow` les masque sur téléphone. */
  extraHeads?: { label: string; narrow?: boolean; width?: string }[];
  /** Clic sur une ligne (filtre de chemin), ou rien si la liste n'est pas cliquable. */
  onSelect?: (key: string) => void;
  activeKey?: string | null;
  limit?: number;
  empty?: string;
  className?: string;
};

/** Classement en barres horizontales proportionnelles, dix lignes puis « voir plus ». */
export function RankList({ title, metric, tone, rows, format, extraHeads = [], onSelect, activeKey, limit = 10, empty = 'Rien à afficher sur cette période.', className }: Props) {
  const [open, setOpen] = useState(false);
  const shown = open ? rows : rows.slice(0, limit);
  const max = Math.max(1, ...rows.map(r => r.value));
  // Colonnes : libellé, mesure, colonnes secondaires (celles marquées `narrow` disparaissent sur téléphone).
  const track = (heads: typeof extraHeads) => `minmax(0, 1fr) 4.2em${heads.map(h => ` ${h.width ?? '4.6em'}`).join('')}`;
  const cols = { '--cols': track(extraHeads), '--cols-narrow': track(extraHeads.filter(h => !h.narrow)) } as CSSProperties;
  const id = `rank-${title.replace(/\W+/g, '-').toLowerCase()}`;

  return (
    <section className={`${s.panel} ${className ?? ''}`} aria-labelledby={id}>
      <header className={s.panelHead}>
        <h2 id={id} className={s.panelTitle}>{title}</h2>
      </header>
      {rows.length === 0 ? <p className={s.empty}>{empty}</p> : (
        <>
          <div className={s.rankHead} style={cols} aria-hidden="true">
            <span />
            <span className={s.num}><span className={`${s.swatch} ${tone === 'views' ? s.keyViews : s.keyVisitors}`} />{metric}</span>
            {extraHeads.map(h => <span key={h.label} className={`${s.num} ${h.narrow ? s.narrowHide : ''}`}>{h.label}</span>)}
          </div>
          <ol className={s.rank}>
            {shown.map(r => {
              const body = (
                <>
                  <span className={s.rowText}>
                    <span className={s.rowLabel} title={r.detail ?? r.label}>{r.label}</span>
                    {r.detail && <span className={s.rowDetail}>{r.detail}</span>}
                  </span>
                  <span className={`${s.num} ${s.rowValue}`}>{format(r.value)}</span>
                  {r.extra?.map((x, i) => <span key={i} className={`${s.num} ${s.rowExtra} ${extraHeads[i]?.narrow ? s.narrowHide : ''}`}>{x}</span>)}
                  <span className={s.barTrack} aria-hidden="true">
                    <span className={`${s.bar} ${tone === 'views' ? s.barViews : s.barVisitors}`} style={{ transform: `scaleX(${r.value / max})` }} />
                  </span>
                </>
              );
              return (
                <li key={r.key} className={activeKey === r.key ? s.rowActive : undefined}>
                  {onSelect
                    ? <button type="button" className={s.rankRow} style={cols} onClick={() => onSelect(r.key)}
                        title={`Filtrer le tableau sur ${r.key}`}>{body}</button>
                    : <div className={s.rankRow} style={cols}>{body}</div>}
                </li>
              );
            })}
          </ol>
          {rows.length > limit && (
            <button type="button" className={s.more} onClick={() => setOpen(o => !o)} aria-expanded={open}>
              {open ? 'Voir moins' : `Voir les ${rows.length} lignes`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
