import type { CollectEvent } from '../../../src/analytics/api.ts';
import { normalizePath } from '../../../src/seo/meta.ts';
import { and, eq, isNull, lt, or } from 'drizzle-orm';
import type { DB } from '../db.ts';
import { pageviews } from '../schema.ts';
import type { Live } from './live.ts';
import { browser, device, isBot, os } from './ua.ts';
import { dayKey, hourStart } from './time.ts';

const ID = /^[A-Za-z0-9_-]{8,40}$/;
const MAX_DURATION = 6 * 3_600_000;

export type CollectContext = { ip: string; ua: string; now: number };
export type CollectResult = 'ok' | 'ignored' | 'invalid';

/** Chemin mesuré : sans requête ni ancre, alias ramenés au chemin principal. */
export function measuredPath(raw: string): string | null {
  if (typeof raw !== 'string' || !raw.startsWith('/') || raw.length > 512) return null;
  // Segments réencodés d'une seule façon : `/lorebook/atlas/a b` et `/lorebook/atlas/a%20b` comptent ensemble.
  try {
    return normalizePath(raw.split(/[?#]/)[0]).split('/').map(seg => encodeURIComponent(decodeURIComponent(seg))).join('/') || '/';
  } catch { return null; }
}

export function sectionOf(path: string): string {
  const first = path.split('/')[1];
  return first ? `/${first}` : '/';
}

/** Provenance : domaine du référent (sans `www.`), étiquette de campagne telle quelle, ou null (direct, interne). */
export function referrerOf(raw: unknown, ownHosts: readonly string[]): string | null {
  if (typeof raw !== 'string' || !raw) return null;
  try {
    const host = new URL(raw).hostname.replace(/^www\./, '').toLowerCase();
    if (!host || ownHosts.some(own => host === own || host.endsWith(`.${own}`))) return null;
    // Moteurs de recherche : un seul libellé par moteur, quel que soit le domaine national.
    const engine = /(^|\.)google\./.test(host) ? 'google.com' : /(^|\.)bing\.com$/.test(host) ? 'bing.com'
      : /(^|\.)yandex\./.test(host) ? 'yandex.ru' : /(^|\.)duckduckgo\.com$/.test(host) ? 'duckduckgo.com' : null;
    return (engine ?? host).slice(0, 100);
  } catch {
    const label = raw.trim().toLowerCase().replace(/[^\p{L}\p{N}._ -]/gu, '').slice(0, 60);
    return label || null;
  }
}

export function createCollector(db: DB, live: Live, visitorOf: (ip: string, ua: string, ts: number) => Promise<string>, ownHosts: readonly string[]) {
  return async function collect(raw: unknown, ctx: CollectContext): Promise<CollectResult> {
    if (isBot(ctx.ua)) return 'ignored';
    if (!raw || typeof raw !== 'object') return 'invalid';
    const ev = raw as Partial<CollectEvent>;
    if (ev.type !== 'view' && ev.type !== 'ping' && ev.type !== 'leave') return 'invalid';
    if (typeof ev.session !== 'string' || !ID.test(ev.session) || typeof ev.view !== 'string' || !ID.test(ev.view)) return 'invalid';
    const path = measuredPath(ev.path as string);
    if (!path) return 'invalid';
    if (path === '/stats') return 'ignored';

    const visitor = await visitorOf(ctx.ip, ctx.ua, ctx.now);
    if (ev.type === 'view') {
      const known = await db.select({ id: pageviews.id }).from(pageviews).where(eq(pageviews.session, ev.session)).limit(1);
      const entry = known.length === 0;
      await db.insert(pageviews).ignore().values({
        id: ev.view, ts: ctx.now, day: dayKey(ctx.now), hour: hourStart(ctx.now), session: ev.session, visitor, path,
        section: sectionOf(path).slice(0, 128), entry, referrer: entry ? referrerOf(ev.referrer, ownHosts) : null,
        lang: ev.lang === 'fr' || ev.lang === 'en' ? ev.lang : null,
        device: device(ctx.ua, typeof ev.width === 'number' ? ev.width : undefined), browser: browser(ctx.ua), os: os(ctx.ua),
      });
    }
    if (typeof ev.duration === 'number' && Number.isFinite(ev.duration) && ev.duration >= 0) {
      const ms = Math.min(Math.round(ev.duration), MAX_DURATION);
      await db.update(pageviews).set({ duration: ms }).where(and(
        eq(pageviews.id, ev.view), eq(pageviews.session, ev.session), or(isNull(pageviews.duration), lt(pageviews.duration, ms)),
      ));
    }
    if (ev.type === 'leave') live.leave(ev.session, ev.view);
    else live.touch(ev.session, { visitor, path, view: ev.view, seen: ctx.now });
    return 'ok';
  };
}

/** Limite de débit par IP (fenêtre glissante d'une minute), en mémoire. */
export function createRateLimiter(perMinute: number) {
  const hits = new Map<string, number[]>();
  let sweep = 0;
  return (key: string, now: number) => {
    if (now - sweep > 60_000) {
      sweep = now;
      for (const [k, list] of hits) if (!list.length || now - list[list.length - 1] > 60_000) hits.delete(k);
    }
    const list = (hits.get(key) ?? []).filter(t => now - t < 60_000);
    list.push(now);
    hits.set(key, list);
    return list.length <= perMinute;
  };
}
