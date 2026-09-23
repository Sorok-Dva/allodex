import { and, count, countDistinct, desc, eq, gte, inArray, lt, or, sql, type SQL } from 'drizzle-orm';
import type { MySqlColumn } from 'drizzle-orm/mysql-core';
import type { Count, Range, StatsResponse, Totals } from '../../../src/analytics/api.ts';
import type { DB } from '../db.ts';
import { pageviews as pv } from '../schema.ts';
import { DAY, HOUR, dayStart, daysBetween, hourStart } from './time.ts';

const LIMIT = 50;

/** Bornes d'une période (`to` exclu, donc maintenant + 1) : 24 h glissantes par heure, sinon des jours parisiens entiers. */
export function rangeBounds(range: Range, now: number): { from: number; to: number; bucket: 'hour' | 'day' } {
  if (range === '24h') return { from: hourStart(now) - 23 * HOUR, to: now + 1, bucket: 'hour' };
  const days = range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : 365;
  return { from: dayStart(dayStart(now) - (days - 1) * DAY + 12 * HOUR), to: now + 1, bucket: 'day' };
}

type Filter = { from: number; to: number; path: string | null };

// Les AVG/SUM de MySQL reviennent en DECIMAL (chaînes) : conversion explicite.
const avgDuration = sql<number>`COALESCE(AVG(${pv.duration}), 0)`.mapWith(Number);
const visitors = countDistinct(pv.visitor);
const views = count();

/** Filtre : la page et ses sous-pages (`/lorebook` compte aussi ses entrées) ; l'accueil seul pour `/`. */
function pathCondition(path: string | null): SQL | undefined {
  if (!path) return undefined;
  if (path === '/') return eq(pv.path, '/');
  const prefix = `${path.replace(/[!%_]/g, c => `!${c}`)}/%`;
  return or(eq(pv.path, path), sql`${pv.path} LIKE ${prefix} ESCAPE '!'`);
}

const inPeriod = (f: Filter, ...extra: (SQL | undefined)[]) =>
  and(gte(pv.ts, f.from), lt(pv.ts, f.to), pathCondition(f.path), ...extra);

/**
 * Colonne avec valeur par défaut. La valeur est écrite en clair (`sql.raw`) : un paramètre `?`
 * dans le SELECT et le GROUP BY ferait échouer ONLY_FULL_GROUP_BY.
 */
const orDefault = (column: MySqlColumn, fallback: string) => sql<string>`COALESCE(${column}, ${sql.raw(`'${fallback}'`)})`;

export function createStats(db: DB) {
  async function totals(f: Filter): Promise<Totals> {
    const [row] = await db.select({ views, visitors, sessions: countDistinct(pv.session), avgDurationMs: avgDuration })
      .from(pv).where(inPeriod(f));
    // Rebond : sessions arrivées sur la période (sur la page filtrée, le cas échéant) sans seconde page vue.
    const perSession = db.select({ session: pv.session, c: count().as('c') })
      .from(pv).where(and(gte(pv.ts, f.from), lt(pv.ts, f.to))).groupBy(pv.session).as('s');
    const entered = db.select({ session: pv.session }).from(pv).where(inPeriod(f, eq(pv.entry, true)));
    const [bounce] = await db.select({ sessions: count(), bounced: sql<number>`COALESCE(SUM(${perSession.c} = 1), 0)`.mapWith(Number) })
      .from(perSession).where(inArray(perSession.session, entered));
    return {
      ...row,
      avgDurationMs: Math.round(row.avgDurationMs),
      bounceRate: bounce.sessions ? bounce.bounced / bounce.sessions : 0,
      viewsPerSession: row.sessions ? row.views / row.sessions : 0,
    };
  }

  function counts(f: Filter, key: SQL | MySqlColumn, ...extra: SQL[]): Promise<Count[]> {
    return db.select({ key: sql<string>`${key}`, visitors, views }).from(pv).where(inPeriod(f, ...extra))
      .groupBy(key).orderBy(desc(visitors), desc(views), key).limit(LIMIT);
  }

  async function series(f: Filter, bucket: 'hour' | 'day') {
    if (bucket === 'hour') {
      const rows = await db.select({ t: pv.hour, visitors, views }).from(pv).where(inPeriod(f)).groupBy(pv.hour);
      const byHour = new Map(rows.map(r => [r.t, r]));
      const out = [];
      for (let t = hourStart(f.from); t < f.to; t += HOUR) out.push(byHour.get(t) ?? { t, visitors: 0, views: 0 });
      return out;
    }
    const rows = await db.select({ day: pv.day, visitors, views }).from(pv).where(inPeriod(f)).groupBy(pv.day);
    const byDay = new Map(rows.map(r => [r.day, r]));
    return daysBetween(f.from, f.to).map(({ key, t }) => ({ t, visitors: byDay.get(key)?.visitors ?? 0, views: byDay.get(key)?.views ?? 0 }));
  }

  return async function stats(range: Range, path: string | null, now: number): Promise<StatsResponse> {
    const { from, to, bucket } = rangeBounds(range, now);
    const f = { from, to, path };
    const entry = eq(pv.entry, true);
    const [current, previous, points, pages, sections, entries, referrers, devices, browsers, systems, langs] = await Promise.all([
      totals(f),
      totals({ from: from - (to - from), to: from, path }),
      series(f, bucket),
      db.select({ key: pv.path, visitors, views, avgDurationMs: avgDuration }).from(pv).where(inPeriod(f))
        .groupBy(pv.path).orderBy(desc(visitors), desc(views), pv.path).limit(LIMIT),
      counts(f, pv.section),
      counts(f, pv.path, entry),
      counts(f, orDefault(pv.referrer, '(direct)'), entry),
      counts(f, orDefault(pv.device, 'desktop')),
      counts(f, orDefault(pv.browser, 'Autre')),
      counts(f, orDefault(pv.os, 'Autre')),
      counts(f, orDefault(pv.lang, '?')),
    ]);
    return {
      range, path, from, to, bucket,
      totals: current, previous, series: points,
      pages: pages.map(p => ({ ...p, avgDurationMs: Math.round(p.avgDurationMs) })),
      sections, entries, referrers, devices, browsers, os: systems, langs,
    };
  };
}

/** Purge des pages vues plus anciennes que la durée de conservation ; renvoie le nombre de lignes supprimées. */
export async function purgeOld(db: DB, retentionDays: number, now: number): Promise<number> {
  const [result] = await db.delete(pv).where(lt(pv.ts, now - retentionDays * DAY));
  return result.affectedRows;
}
