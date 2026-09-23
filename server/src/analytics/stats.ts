import type { Count, Range, StatsResponse, Totals } from '../../../src/analytics/api.ts';
import type { DB } from '../db.ts';
import { DAY, HOUR, dayStart, daysBetween, hourStart } from './time.ts';

const LIMIT = 50;

/** Bornes d'une période (`to` exclu, donc maintenant + 1) : 24 h glissantes par heure, sinon des jours parisiens entiers. */
export function rangeBounds(range: Range, now: number): { from: number; to: number; bucket: 'hour' | 'day' } {
  if (range === '24h') return { from: hourStart(now) - 23 * HOUR, to: now + 1, bucket: 'hour' };
  const days = range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : 365;
  return { from: dayStart(dayStart(now) - (days - 1) * DAY + 12 * HOUR), to: now + 1, bucket: 'day' };
}

type Filter = { from: number; to: number; path: string | null };

export function createStats(db: DB) {
  // Filtre : la page et ses sous-pages (`/lorebook` compte aussi ses entrées) ; l'accueil seul pour `/`.
  const pathClause = (f: Filter) => !f.path ? '' : f.path === '/' ? ' AND path = @path' : " AND (path = @path OR path LIKE @prefix ESCAPE '\\')";
  const where = (f: Filter, extra = '') => `WHERE ts >= @from AND ts < @to${pathClause(f)}${extra}`;
  const params = (f: Filter) => ({
    from: f.from, to: f.to,
    ...(f.path ? { path: f.path } : {}),
    ...(f.path && f.path !== '/' ? { prefix: `${f.path.replace(/[\\%_]/g, c => `\\${c}`)}/%` } : {}),
  });
  const cache = new Map<string, ReturnType<DB['prepare']>>();
  const q = (sql: string) => {
    let st = cache.get(sql);
    if (!st) cache.set(sql, st = db.prepare(sql));
    return st;
  };

  function totals(f: Filter): Totals {
    const row = q(`SELECT COUNT(*) views, COUNT(DISTINCT visitor) visitors, COUNT(DISTINCT session) sessions,
      COALESCE(AVG(duration), 0) avgDurationMs FROM pageviews ${where(f)}`).get(params(f)) as Omit<Totals, 'bounceRate' | 'viewsPerSession'>;
    // Rebond : sessions arrivées sur la période (sur la page filtrée, le cas échéant) sans seconde page vue.
    const bounce = q(`WITH s AS (
        SELECT session, COUNT(*) c FROM pageviews WHERE ts >= @from AND ts < @to GROUP BY session
      )
      SELECT COUNT(*) sessions, COALESCE(SUM(c = 1), 0) bounced FROM s
      WHERE session IN (SELECT session FROM pageviews ${where(f, ' AND entry = 1')})`).get(params(f)) as { sessions: number; bounced: number };
    return {
      ...row,
      avgDurationMs: Math.round(row.avgDurationMs),
      bounceRate: bounce.sessions ? bounce.bounced / bounce.sessions : 0,
      viewsPerSession: row.sessions ? row.views / row.sessions : 0,
    };
  }

  function counts(f: Filter, column: string, extra = ''): Count[] {
    return q(`SELECT ${column} key, COUNT(DISTINCT visitor) visitors, COUNT(*) views FROM pageviews ${where(f, extra)}
      GROUP BY key ORDER BY visitors DESC, views DESC, key LIMIT ${LIMIT}`).all(params(f)) as Count[];
  }

  function series(f: Filter, bucket: 'hour' | 'day') {
    if (bucket === 'hour') {
      const rows = q(`SELECT hour t, COUNT(DISTINCT visitor) visitors, COUNT(*) views FROM pageviews ${where(f)} GROUP BY hour`)
        .all(params(f)) as { t: number; visitors: number; views: number }[];
      const byHour = new Map(rows.map(r => [r.t, r]));
      const out = [];
      for (let t = hourStart(f.from); t < f.to; t += HOUR) out.push(byHour.get(t) ?? { t, visitors: 0, views: 0 });
      return out;
    }
    const rows = q(`SELECT day, COUNT(DISTINCT visitor) visitors, COUNT(*) views FROM pageviews ${where(f)} GROUP BY day`)
      .all(params(f)) as { day: string; visitors: number; views: number }[];
    const byDay = new Map(rows.map(r => [r.day, r]));
    return daysBetween(f.from, f.to).map(({ key, t }) => ({ t, visitors: byDay.get(key)?.visitors ?? 0, views: byDay.get(key)?.views ?? 0 }));
  }

  return function stats(range: Range, path: string | null, now: number): StatsResponse {
    const { from, to, bucket } = rangeBounds(range, now);
    const f = { from, to, path };
    const pages = q(`SELECT path key, COUNT(DISTINCT visitor) visitors, COUNT(*) views, COALESCE(AVG(duration), 0) avgDurationMs
      FROM pageviews ${where(f)} GROUP BY path ORDER BY visitors DESC, views DESC, path LIMIT ${LIMIT}`)
      .all(params(f)) as (Count & { avgDurationMs: number })[];
    return {
      range, path, from, to, bucket,
      totals: totals(f),
      previous: totals({ from: from - (to - from), to: from, path }),
      series: series(f, bucket),
      pages: pages.map(p => ({ ...p, avgDurationMs: Math.round(p.avgDurationMs) })),
      sections: counts(f, 'section'),
      entries: counts(f, 'path', ' AND entry = 1'),
      referrers: counts(f, "COALESCE(referrer, '(direct)')", ' AND entry = 1'),
      devices: counts(f, "COALESCE(device, 'desktop')"),
      browsers: counts(f, "COALESCE(browser, 'Autre')"),
      os: counts(f, "COALESCE(os, 'Autre')"),
      langs: counts(f, "COALESCE(lang, '?')"),
    };
  };
}

/** Purge des pages vues plus anciennes que la durée de conservation. */
export function purgeOld(db: DB, retentionDays: number, now: number) {
  return db.prepare('DELETE FROM pageviews WHERE ts < ?').run(now - retentionDays * DAY).changes;
}
