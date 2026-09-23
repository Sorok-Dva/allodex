import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { RANGES, type LiveSnapshot, type Range, type StatsResponse, type Totals } from '@/analytics/api';
import { T, tex } from '@/lib/assets';
import { Link, navigate, useRoute } from '@/lib/router';
import { httpSource, UnauthorizedError, type LiveStatus, type StatsSource } from './client';
import {
  RANGE_LABELS, deviceLabel, formatAgo, formatCount, formatDecimal, formatDuration, formatPercent, formatTrend,
  langLabel, parseScreenQuery, pathLabel, referrerLabel, screenUrl, trend, type ScreenQuery,
} from './format';
import { LivePanel } from './LivePanel';
import { RankList, type RankRow } from './RankList';
import { TalentsPanel } from './TalentsPanel';
import { TrafficChart, TrafficTable } from './TrafficChart';
import s from './StatsScreen.module.css';

/**
 * Maquette du backend (`/stats?mock`) : en développement seulement. Au build, la condition
 * devient `false` et l'import dynamique disparaît du bundle de production.
 */
const loadMock = import.meta.env.DEV ? () => import('./mock') : null;

/** Rafraîchissement automatique des statistiques. */
const REFRESH_MS = 60_000;
const PLATE = 'Interface/Ingame/Contextructor/WindowHeader/TiledHeader';

/** Titre de l'onglet et `noindex` le temps que l'écran est monté. */
function usePageMeta() {
  useEffect(() => {
    document.title = 'Statistiques — Allodex';
    // La page d'accueil sert déjà un `robots` (index,follow) : on le passe en `noindex` et on
    // le rétablit en partant ; à défaut, on pose une balise que l'on retire au démontage.
    const existing = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (existing) {
      const previous = existing.content;
      existing.content = 'noindex';
      return () => { existing.content = previous; };
    }
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex';
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);
}

type Auth = 'checking' | 'anon' | 'authed' | 'unreachable';

export default function StatsScreen() {
  const { query } = useRoute();
  const q = parseScreenQuery(query);
  const mock = Boolean(loadMock) && q.mock;
  const [source, setSource] = useState<StatsSource | null>(mock ? null : httpSource);
  const [auth, setAuth] = useState<Auth>('checking');
  usePageMeta();

  useEffect(() => {
    if (mock && loadMock) loadMock().then(m => setSource(m.mockSource));
  }, [mock]);

  const check = useCallback(() => {
    if (!source) return;
    setAuth('checking');
    source.me().then(ok => setAuth(ok ? 'authed' : 'anon'), () => setAuth('unreachable'));
  }, [source]);
  useEffect(check, [check]);

  const background = { backgroundImage: `url(${tex(`${T.main2}/Background_14_0_Temp`)})` };

  if (!source || auth === 'checking') return <main className={s.screen} style={background}><div className={s.shade} /><p className={s.boot}>Chargement…</p></main>;
  if (auth === 'anon' || auth === 'unreachable') {
    return (
      <main className={s.screen} style={background}>
        <div className={s.shade} />
        <Login source={source} unreachable={auth === 'unreachable'} onRetry={check} onDone={() => setAuth('authed')} />
      </main>
    );
  }
  return (
    <main className={s.screen} style={background}>
      <div className={s.shade} />
      <Dashboard source={source} query={q} onUnauthorized={() => setAuth('anon')} />
    </main>
  );
}

// --- connexion -----------------------------------------------------------------------------

function Plate({ children }: { children: ReactNode }) {
  return (
    <div className={s.plate}>
      <span className={s.plateSkin} aria-hidden="true" style={{ borderImageSource: `url(${tex(PLATE)})` }} />
      <h1 className={s.title}>{children}</h1>
    </div>
  );
}

function Login({ source, unreachable, onRetry, onDone }: { source: StatsSource; unreachable: boolean; onRetry: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (await source.login(password)) onDone();
      else { setError('Mot de passe refusé.'); setPassword(''); input.current?.focus(); }
    } catch (err) {
      setError(`Connexion impossible (${err instanceof Error ? err.message : 'erreur réseau'}). Réessayez dans un instant.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={s.loginWrap}>
      <form className={`${s.panel} ${s.login}`} onSubmit={submit}>
        <Plate>Statistiques</Plate>
        <p className={s.loginIntro}>Tableau d'audience d'Allodex, réservé à l'administration.</p>
        {unreachable && (
          <p className={s.alert} role="alert">
            Le serveur d'audience ne répond pas.{' '}
            <button type="button" className={s.linkButton} onClick={onRetry}>Réessayer</button>
          </p>
        )}
        <label className={s.field}>
          <span>Mot de passe</span>
          <input ref={input} type="password" autoComplete="current-password" value={password}
            onChange={e => setPassword(e.target.value)} aria-invalid={error ? true : undefined} aria-describedby={error ? 'login-error' : undefined} />
        </label>
        {error && <p id="login-error" className={s.alert} role="alert">{error}</p>}
        <button type="submit" className={s.gameButton} disabled={busy || !password}>{busy ? 'Connexion…' : 'Se connecter'}</button>
        <Link to="/" className={s.back}>‹ Retour à l'accueil</Link>
      </form>
    </div>
  );
}

// --- données -------------------------------------------------------------------------------

type StatsState = { data: StatsResponse | null; error: string | null; loading: boolean; updatedAt: number | null };

function useStats(source: StatsSource, range: Range, path: string | null, onUnauthorized: () => void) {
  const [state, setState] = useState<StatsState>({ data: null, error: null, loading: true, updatedAt: null });
  const [nonce, setNonce] = useState(0);
  const unauthorized = useRef(onUnauthorized);
  unauthorized.current = onUnauthorized;

  useEffect(() => {
    const ctrl = new AbortController();
    setState(st => ({ ...st, loading: true }));
    source.stats(range, path, ctrl.signal).then(
      data => { if (!ctrl.signal.aborted) setState({ data, error: null, loading: false, updatedAt: Date.now() }); },
      err => {
        if (ctrl.signal.aborted) return;
        if (err instanceof UnauthorizedError) { unauthorized.current(); return; }
        setState(st => ({ ...st, loading: false, error: err instanceof Error ? err.message : String(err) }));
      },
    );
    const id = setTimeout(() => setNonce(n => n + 1), REFRESH_MS);
    return () => { ctrl.abort(); clearTimeout(id); };
  }, [source, range, path, nonce]);

  return { ...state, reload: () => setNonce(n => n + 1) };
}

function useLive(source: StatsSource, onUnauthorized: () => void) {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [status, setStatus] = useState<LiveStatus>('connecting');
  const unauthorized = useRef(onUnauthorized);
  unauthorized.current = onUnauthorized;
  useEffect(() => source.live({ onSnapshot: setSnapshot, onStatus: setStatus, onUnauthorized: () => unauthorized.current() }), [source]);
  return { snapshot, status };
}

// --- tableau de bord ------------------------------------------------------------------------

type Kpi = { key: keyof Totals; label: string; short?: string; format: (n: number) => string; lowerIsBetter?: boolean };
const KPIS: Kpi[] = [
  { key: 'visitors', label: 'Visiteurs', format: formatCount },
  { key: 'views', label: 'Pages vues', format: formatCount },
  { key: 'sessions', label: 'Sessions', format: formatCount },
  { key: 'avgDurationMs', label: 'Durée moyenne par page', short: 'Durée par page', format: formatDuration },
  { key: 'bounceRate', label: 'Taux de rebond', format: v => formatPercent(v, 1), lowerIsBetter: true },
  { key: 'viewsPerSession', label: 'Pages par session', format: formatDecimal },
];

function KpiTile({ kpi, totals, previous, range }: { kpi: Kpi; totals: Totals; previous: Totals; range: Range }) {
  const t = trend(totals[kpi.key], previous[kpi.key], kpi.lowerIsBetter);
  const arrow = t.direction === 'up' ? '▲' : t.direction === 'down' ? '▼' : '■';
  const reading = t.tone === 'good' ? 'bonne évolution' : t.tone === 'bad' ? 'évolution défavorable' : '';
  return (
    <div className={s.kpi}>
      <div className={s.kpiLabel}>
        {kpi.short ? <><span className={s.wideOnly}>{kpi.label}</span><span className={s.narrowOnly}>{kpi.short}</span></> : kpi.label}
      </div>
      <div className={s.kpiValue}>{kpi.format(totals[kpi.key])}</div>
      <div className={`${s.delta} ${s[`delta_${t.tone}`]}`} title={`${kpi.format(previous[kpi.key])} sur ${RANGE_LABELS[range].previous}`}>
        {t.ratio !== null && <span aria-hidden="true" className={s.deltaArrow}>{arrow}</span>}
        <span>{formatTrend(t)}</span>
        <span className={s.deltaRef}>
          <span className={s.srOnly}>{reading ? `, ${reading}, ` : ' '}par rapport à {RANGE_LABELS[range].previous}</span>
          <span className={s.wideOnly} aria-hidden="true">vs {RANGE_LABELS[range].previous}</span>
          <span className={s.narrowOnly} aria-hidden="true">vs {RANGE_LABELS[range].previousTiny}</span>
        </span>
      </div>
    </div>
  );
}

function UpdatedAgo({ at }: { at: number | null }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(id); }, []);
  if (!at) return null;
  return <>Actualisé {formatAgo(at, Math.max(now, at))}</>;
}

const share = (total: number) => (n: number) => (total > 0 ? formatPercent(n / total) : '—');

function Dashboard({ source, query, onUnauthorized }: { source: StatsSource; query: ScreenQuery; onUnauthorized: () => void }) {
  const { range, path } = query;
  const stats = useStats(source, range, path, onUnauthorized);
  const live = useLive(source, onUnauthorized);
  const data = stats.data;
  const set = (next: Partial<ScreenQuery>) => navigate(screenUrl({ ...query, ...next }), { replace: true });
  const selectPath = (p: string) => set({ path: p === path ? null : p });
  const [chartH, setChartH] = useState(() => (window.innerWidth < 640 ? 210 : 260));
  useEffect(() => {
    const onResize = () => setChartH(window.innerWidth < 640 ? 210 : 260);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const logout = async () => {
    try { await source.logout(); } finally { onUnauthorized(); }
  };

  const lists = useMemo(() => {
    if (!data) return null;
    const visitorsTotal = data.totals.visitors;
    const pageRows: RankRow[] = data.pages.map(p => ({
      key: p.key, ...pathLabel(p.key), value: p.views, extra: [formatCount(p.visitors), formatDuration(p.avgDurationMs)],
    }));
    const pathRows = (list: StatsResponse['sections']): RankRow[] =>
      list.map(c => ({ key: c.key, ...pathLabel(c.key), value: c.views, extra: [formatCount(c.visitors)] }));
    const entryRows: RankRow[] = data.entries.map(c => ({ key: c.key, ...pathLabel(c.key), value: c.visitors, extra: [formatCount(c.views)] }));
    const shareRows = (list: StatsResponse['referrers'], label: (k: string) => string = k => k): RankRow[] =>
      list.map(c => ({ key: c.key, label: label(c.key), value: c.visitors, extra: [share(visitorsTotal)(c.visitors)] }));
    return {
      pages: pageRows,
      sections: pathRows(data.sections),
      entries: entryRows,
      referrers: shareRows(data.referrers, referrerLabel),
      devices: shareRows(data.devices, deviceLabel),
      browsers: shareRows(data.browsers),
      os: shareRows(data.os),
      langs: shareRows(data.langs, langLabel),
    };
  }, [data]);

  const filterLabel = path ? pathLabel(path) : null;
  const empty = data !== null && data.totals.views === 0;
  const stale = stats.loading && data !== null && (data.range !== range || data.path !== path);

  return (
    <div className={s.page}>
      <header className={s.top}>
        <Link to="/" className={s.back}>‹ Accueil</Link>
        <Plate>Statistiques</Plate>
        <div className={s.topRight}>
          <div className={`${s.liveBadge} ${live.status === 'open' ? '' : s.liveBadgeOff}`} title="Visiteurs sur le site en ce moment">
            <span className={s.pulse} aria-hidden="true" />
            <strong key={live.snapshot?.total} className={s.bump}>{live.snapshot ? formatCount(live.snapshot.total) : '—'}</strong>
            <span>en direct</span>
          </div>
          <button type="button" className={s.ghostButton} onClick={logout}>Se déconnecter</button>
        </div>
      </header>

      <div className={s.toolbar}>
        <div className={s.ranges} role="group" aria-label="Période">
          {RANGES.map(r => (
            <button key={r} type="button" className={`${s.range} ${r === range ? s.rangeActive : ''}`} aria-pressed={r === range} aria-label={RANGE_LABELS[r].short} onClick={() => set({ range: r })}>
              <span className={s.wideOnly} aria-hidden="true">{RANGE_LABELS[r].short}</span>
              <span className={s.narrowOnly} aria-hidden="true">{RANGE_LABELS[r].tiny}</span>
            </button>
          ))}
        </div>
        {path && filterLabel && (
          <button type="button" className={s.chip} onClick={() => set({ path: null })} aria-label={`Retirer le filtre ${path}`}>
            <span className={s.chipLabel}>Filtre : <strong>{filterLabel.detail ? `${filterLabel.label} (${path})` : filterLabel.label}</strong></span>
            <span className={s.chipClose} aria-hidden="true">✕</span>
          </button>
        )}
        <div className={s.updated}>
          <span aria-live="polite">{stats.loading ? 'Actualisation…' : <UpdatedAgo at={stats.updatedAt} />}</span>
          <button type="button" className={s.iconButton} onClick={stats.reload} aria-label="Actualiser maintenant" title="Actualiser maintenant" disabled={stats.loading}>
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </div>
      </div>

      {stats.error && data && (
        <p className={s.banner} role="alert">
          Échec de l'actualisation ({stats.error}) : les chiffres affichés datent de la mise à jour précédente.{' '}
          <button type="button" className={s.linkButton} onClick={stats.reload}>Réessayer</button>
        </p>
      )}

      {!data && stats.error && (
        <div className={`${s.panel} ${s.state}`} role="alert">
          <h2 className={s.panelTitle}>Statistiques indisponibles</h2>
          <p>Le serveur n'a pas renvoyé les chiffres ({stats.error}).</p>
          <button type="button" className={s.gameButton} onClick={stats.reload}>Réessayer</button>
        </div>
      )}

      {!data && !stats.error && <div className={`${s.panel} ${s.state}`}><p className={s.loading}>Chargement des statistiques…</p></div>}

      {data && lists && (
        <div className={`${s.content} ${stale ? s.stale : ''}`} aria-busy={stats.loading}>
          <p className={s.scope}>
            {path ? <>Page <strong>{path}</strong> sur {RANGE_LABELS[range].long}</> : <>Tout le site sur {RANGE_LABELS[range].long}</>}
          </p>
          <div className={s.kpis}>
            {KPIS.map(k => <KpiTile key={k.key} kpi={k} totals={data.totals} previous={data.previous} range={range} />)}
          </div>

          <div className={s.mainRow}>
            <section className={`${s.panel} ${s.chartPanel}`} aria-labelledby="traffic-title">
              <header className={s.panelHead}>
                <h2 id="traffic-title" className={s.panelTitle}>Fréquentation {data.bucket === 'hour' ? 'par heure' : 'par jour'}</h2>
                <ul className={s.legend}>
                  <li><span className={`${s.swatch} ${s.keyVisitors}`} />Visiteurs</li>
                  <li><span className={`${s.swatch} ${s.keyViews}`} />Pages vues</li>
                </ul>
              </header>
              <div className={s.chartWrap}>
                <TrafficChart series={data.series} bucket={data.bucket} minHeight={chartH} />
                {empty && <p className={s.chartEmpty}>Aucune visite sur {RANGE_LABELS[range].long}.</p>}
              </div>
              {!empty && <TrafficTable series={data.series} bucket={data.bucket} />}
            </section>
            <LivePanel snapshot={live.snapshot} status={live.status} activePath={path} onSelect={selectPath} />
          </div>

          <div className={s.ranksRow}>
            <RankList title="Pages" metric="Vues" tone="views" rows={lists.pages} format={formatCount}
              extraHeads={[{ label: 'Visiteurs', narrow: true }, { label: 'Durée', width: '6.2em' }]} onSelect={selectPath} activeKey={path} className={s.wide} />
            <RankList title="Rubriques" metric="Vues" tone="views" rows={lists.sections} format={formatCount}
              extraHeads={[{ label: 'Visiteurs' }]} onSelect={selectPath} activeKey={path} />
            <RankList title="Pages d'arrivée" metric="Visiteurs" tone="visitors" rows={lists.entries} format={formatCount}
              extraHeads={[{ label: 'Vues' }]} onSelect={selectPath} activeKey={path} />
            <RankList title="Référents" metric="Visiteurs" tone="visitors" rows={lists.referrers} format={formatCount} extraHeads={[{ label: 'Part' }]} />
          </div>

          <div className={s.techRow}>
            <RankList title="Appareils" metric="Visiteurs" tone="visitors" rows={lists.devices} format={formatCount} extraHeads={[{ label: 'Part' }]} />
            <RankList title="Navigateurs" metric="Visiteurs" tone="visitors" rows={lists.browsers} format={formatCount} extraHeads={[{ label: 'Part' }]} />
            <RankList title="Systèmes" metric="Visiteurs" tone="visitors" rows={lists.os} format={formatCount} extraHeads={[{ label: 'Part' }]} />
            <RankList title="Langues" metric="Visiteurs" tone="visitors" rows={lists.langs} format={formatCount} extraHeads={[{ label: 'Part' }]} />
          </div>
          <TalentsPanel source={source} range={range} onUnauthorized={onUnauthorized} />
          <p className={s.footnote}>
            Mesure sans cookie : un visiteur est compté une fois par jour et par navigateur (et par build pour le calculateur). Heures de Paris.
          </p>
        </div>
      )}
    </div>
  );
}
