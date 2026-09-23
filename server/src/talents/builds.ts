import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { and, desc, eq, gte, lt, sql } from 'drizzle-orm';
import type { MySqlColumn } from 'drizzle-orm/mysql-core';
import { TALENT_EVENT_KINDS, type Range, type TalentCounts, type TalentEventKind, type TalentStatsResponse } from '../../../src/analytics/api.ts';
import { checkShared, decodeBuild, rulesFor } from '../../../src/data/talents.build.ts';
import type { ClassTalents, TalentsIndex, UiLayout } from '../../../src/data/talents.types.ts';
import type { DB } from '../db.ts';
import { talentBuildEvents as ev, talentBuilds as tb } from '../schema.ts';
import type { CollectContext, CollectResult } from '../analytics/collect.ts';
import { rangeBounds } from '../analytics/stats.ts';
import { DAY, dayKey } from '../analytics/time.ts';
import { isBot } from '../analytics/ua.ts';

/**
 * Registre des builds du calculateur de talents : chaque build composé, partagé ou ouvert
 * depuis un lien est écrit dans `talent_builds` (une ligne par contenu) et chaque événement
 * dans `talent_build_events`, une fois par visiteur, par jour et par sorte.
 */

const MAX_CODE = 255;
const CODE = /^[0-9A-Za-z._-]+$/;
const TOP = 20;

/** Identifiant du build : condensat de la version, de la classe et des deux codes. */
export function buildId(v: string, c: string, b: string | null, b2: string | null): string {
  return createHash('sha256').update(`${v}|${c}|${b ?? ''}|${b2 ?? ''}`).digest('base64url').slice(0, 12);
}

export type BuildValidator = (v: string, c: string, b: string | null, b2: string | null) => Promise<boolean>;

/**
 * Vérifie un build contre les données publiées (`dist/game/talents/`) avec les règles du
 * calculateur : version et classe connues, codes décodables et conformes. Fichiers lus une
 * fois (la version et la classe sont validées par l'index avant tout accès disque).
 */
export function createBuildValidator(distDir: string): BuildValidator {
  const root = path.join(distDir, 'game', 'talents');
  const files = new Map<string, Promise<unknown>>();
  const read = <T>(rel: string): Promise<T> => {
    let p = files.get(rel);
    if (!p) {
      p = fs.readFile(path.join(root, rel), 'utf8').then(JSON.parse);
      p.catch(() => files.delete(rel));
      files.set(rel, p);
    }
    return p as Promise<T>;
  };
  return async (v, c, b, b2) => {
    try {
      const index = await read<TalentsIndex>('index.json');
      if (checkShared(index, v, c)) return false;
      const version = index.versions.find(x => x.id === v)!;
      const [data, ui] = await Promise.all([read<ClassTalents>(`${v}/${c}.json`), read<UiLayout>('ui/talent_builder.json')]);
      const calc = { data, rules: rulesFor(version.points ?? null, ui.layout.rankCost) };
      return [b, b2].every(code => code === null || decodeBuild(calc, code).ok);
    } catch {
      return false;
    }
  };
}

const COUNTERS = { generate: 'generations', share: 'shares', view: 'views' } as const;

const code = (raw: unknown): string | null | undefined => {
  if (raw === undefined || raw === null || raw === '') return null;
  return typeof raw === 'string' && raw.length <= MAX_CODE && CODE.test(raw) ? raw : undefined;
};

export function createTalentRecorder(db: DB, visitorOf: (ip: string, ua: string, ts: number) => Promise<string>, validate: BuildValidator) {
  return async function record(raw: unknown, ctx: CollectContext): Promise<CollectResult> {
    if (isBot(ctx.ua)) return 'ignored';
    if (!raw || typeof raw !== 'object') return 'invalid';
    const e = raw as Record<string, unknown>;
    const kind = e.kind as TalentEventKind;
    if (!TALENT_EVENT_KINDS.includes(kind)) return 'invalid';
    if (typeof e.v !== 'string' || e.v.length > 16 || typeof e.c !== 'string' || e.c.length > 32) return 'invalid';
    const b = code(e.b), b2 = code(e.b2);
    if (b === undefined || b2 === undefined || (b === null && b2 === null)) return 'invalid';
    if (!(await validate(e.v, e.c, b, b2))) return 'invalid';

    const id = buildId(e.v, e.c, b, b2);
    const visitor = await visitorOf(ctx.ip, ctx.ua, ctx.now);
    const day = dayKey(ctx.now);
    await db.insert(tb).ignore().values({ id, version: e.v, cls: e.c, b, b2, firstTs: ctx.now, lastTs: ctx.now });
    if (kind === 'view') {
      // Son propre build, rouvert le jour même (rechargement, lien collé chez soi) : pas une vue.
      const own = await db.select({ id: ev.id }).from(ev)
        .where(and(eq(ev.build, id), eq(ev.kind, 'generate'), eq(ev.day, day), eq(ev.visitor, visitor))).limit(1);
      if (own.length) return 'ignored';
    }
    const [inserted] = await db.insert(ev).ignore().values({
      build: id, kind, ts: ctx.now, day, visitor, lang: e.lang === 'fr' || e.lang === 'en' ? e.lang : null,
    });
    if (!inserted.affectedRows) return 'ignored';
    const counter = COUNTERS[kind];
    await db.update(tb).set({ [counter]: sql`${tb[counter]} + 1`, lastTs: ctx.now }).where(eq(tb.id, id));
    return 'ok';
  };
}

// Sommes par sorte d'événement ; valeurs écrites en clair (pas de paramètre `?` dans le SELECT).
const sumKind = (kind: TalentEventKind) => sql<number>`COALESCE(SUM(${ev.kind} = ${sql.raw(`'${kind}'`)}), 0)`.mapWith(Number);
const activity = { generations: sumKind('generate'), shares: sumKind('share'), views: sumKind('view') };
const composed = sql<number>`COUNT(DISTINCT CASE WHEN ${ev.kind} = 'generate' THEN ${ev.build} END)`.mapWith(Number);
const sum = (column: MySqlColumn) => sql<number>`COALESCE(SUM(${column}), 0)`.mapWith(Number);

export function createTalentStats(db: DB) {
  return async (range: Range, now: number): Promise<TalentStatsResponse> => {
    const { from, to } = rangeBounds(range, now);
    const inPeriod = and(gte(ev.ts, from), lt(ev.ts, to));
    const [[totals], [allTime], classes, top] = await Promise.all([
      db.select({ builds: composed, ...activity }).from(ev).where(inPeriod),
      db.select({
        builds: sql<number>`COALESCE(SUM(${tb.generations} > 0), 0)`.mapWith(Number),
        generations: sum(tb.generations), shares: sum(tb.shares), views: sum(tb.views),
      }).from(tb),
      db.select({ version: tb.version, cls: tb.cls, builds: composed, ...activity })
        .from(ev).innerJoin(tb, eq(ev.build, tb.id)).where(inPeriod)
        .groupBy(tb.version, tb.cls).orderBy(desc(composed), desc(activity.views)),
      db.select({
        id: tb.id, version: tb.version, cls: tb.cls, b: tb.b, b2: tb.b2, playerId: tb.playerId, firstTs: tb.firstTs,
        totalGenerations: tb.generations, totalShares: tb.shares, totalViews: tb.views, ...activity,
      }).from(ev).innerJoin(tb, eq(ev.build, tb.id)).where(inPeriod)
        .groupBy(tb.id).orderBy(desc(activity.views), desc(activity.shares), desc(activity.generations), desc(tb.firstTs)).limit(TOP),
    ]);
    return {
      range, from, to,
      totals: totals as TalentCounts,
      allTime: allTime as TalentCounts,
      classes,
      top: top.map(r => ({
        id: r.id, version: r.version, cls: r.cls, b: r.b, b2: r.b2, playerId: r.playerId, firstTs: r.firstTs,
        period: { generations: r.generations, shares: r.shares, views: r.views },
        total: { generations: r.totalGenerations, shares: r.totalShares, views: r.totalViews },
      })),
    };
  };
}

/** Efface les événements plus anciens que la durée de conservation ; les builds et leurs compteurs restent. */
export async function purgeOldTalentEvents(db: DB, retentionDays: number, now: number): Promise<number> {
  const [result] = await db.delete(ev).where(lt(ev.ts, now - retentionDays * DAY));
  return result.affectedRows;
}

