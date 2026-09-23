/**
 * Maquette du backend d'audience, pour développer `/stats` sans serveur (`/stats?mock`,
 * en développement seulement : `StatsScreen` ne l'importe que sous `import.meta.env.DEV`).
 * Données crédibles et stables d'un rendu à l'autre (générateur pseudo-aléatoire à graine).
 */
import type { Count, LiveSnapshot, Range, StatsResponse, Totals } from '@/analytics/api';
import type { StatsSource } from './client';
import { parisParts } from './format';

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

/** Générateur mulberry32 : même graine, même suite. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Poids relatifs des pages (vues) et durée moyenne passée dessus. */
const PAGES: { path: string; weight: number; durationS: number }[] = [
  { path: '/', weight: 100, durationS: 48 },
  { path: '/talents', weight: 62, durationS: 312 },
  { path: '/lorebook', weight: 44, durationS: 71 },
  { path: '/music', weight: 31, durationS: 405 },
  { path: '/chronicles', weight: 27, durationS: 188 },
  { path: '/achievements', weight: 19, durationS: 142 },
  { path: '/cinematics', weight: 15, durationS: 356 },
  { path: '/lorebook/characters/r425694', weight: 9, durationS: 96 },
  { path: '/lorebook/atlas/r112037', weight: 7.5, durationS: 83 },
  { path: '/lorebook/quests/r301455', weight: 6, durationS: 64 },
  { path: '/lorebook/library/r87120', weight: 5.2, durationS: 138 },
  { path: '/lorebook/timeline', weight: 4.4, durationS: 121 },
  { path: '/lorebook/characters/r390011', weight: 3.1, durationS: 58 },
  { path: '/fatalities', weight: 2.6, durationS: 97 },
  { path: '/terms', weight: 1.1, durationS: 35 },
];
const PAGE_WEIGHT = PAGES.reduce((s, p) => s + p.weight, 0);

const REFERRERS: [string, number][] = [
  ['(direct)', 41], ['google.com', 27], ['discord.com', 14], ['reddit.com', 6.5], ['allods.mail.ru', 4],
  ['bing.com', 2.5], ['duckduckgo.com', 1.8], ['youtube.com', 1.4], ['t.me', 0.9], ['vk.com', 0.6], ['forum.allods.ru', 0.3],
];
const DEVICES: [string, number][] = [['desktop', 71], ['mobile', 25], ['tablet', 4]];
const BROWSERS: [string, number][] = [['Chrome', 52], ['Firefox', 21], ['Edge', 9], ['Safari', 8], ['Opera', 6], ['Yandex', 3], ['Samsung Internet', 1]];
const OS: [string, number][] = [['Windows', 64], ['Android', 16], ['iOS', 9], ['macOS', 5], ['Linux', 5], ['ChromeOS', 1]];
const LANGS: [string, number][] = [['fr', 68], ['en', 32]];

/** Fréquentation relative selon l'heure de Paris : creux vers 5 h, pointe vers 21 h. */
const hourWeight = (h: number) => 0.18 + 0.82 * Math.max(0, Math.sin(((h - 6) / 24) * Math.PI * 2 - 0.9) * 0.5 + 0.5) ** 1.6;

const RANGE_SPAN: Record<Range, number> = { '24h': DAY, '7d': 7 * DAY, '30d': 30 * DAY, '90d': 90 * DAY, '12m': 365 * DAY };

function split(entries: [string, number][], visitors: number, views: number, rand: () => number): Count[] {
  const total = entries.reduce((s, [, w]) => s + w, 0);
  return entries
    .map(([key, w]) => {
      const share = (w / total) * (0.85 + rand() * 0.3);
      return { key, visitors: Math.round(visitors * share), views: Math.round(views * share) };
    })
    .filter(c => c.visitors > 0 || c.views > 0)
    .sort((a, b) => b.visitors - a.visitors);
}

function totalsFor(visitors: number, views: number, rand: () => number, durationS: number): Totals {
  const sessions = Math.max(visitors, Math.round(visitors * (1.18 + rand() * 0.2)));
  return {
    visitors,
    views,
    sessions,
    avgDurationMs: Math.round((durationS * (0.85 + rand() * 0.3)) * 1000),
    bounceRate: 0.34 + rand() * 0.14,
    viewsPerSession: sessions ? views / sessions : 0,
  };
}

export function mockStats(range: Range, path: string | null, now = Date.now()): StatsResponse {
  const rand = rng(range.length * 7919 + (path?.length ?? 0) * 104729 + 17);
  const bucket = range === '24h' || range === '7d' ? 'hour' : 'day';
  const step = bucket === 'hour' ? HOUR : DAY;
  const to = Math.floor(now / step) * step + step;
  const from = to - RANGE_SPAN[range];
  const page = path ? PAGES.find(p => p.path === path || p.path.startsWith(`${path}/`)) : null;
  // Part de trafic du filtre (une rubrique cumule ses sous-pages).
  const share = path
    ? PAGES.filter(p => p.path === path || (path !== '/' && p.path.startsWith(`${path}/`))).reduce((s, p) => s + p.weight, 0) / PAGE_WEIGHT || 0.01
    : 1;

  const series: StatsResponse['series'] = [];
  const base = (bucket === 'hour' ? 34 : 520) * share;
  for (let t = from; t < to; t += step) {
    const p = parisParts(t);
    const weekday = new Date(t).getUTCDay();
    const weekend = weekday === 0 || weekday === 6 ? 1.22 : 1;
    const growth = 1 + ((t - from) / (to - from)) * 0.25;
    let w = (bucket === 'hour' ? hourWeight(p.hour) : 1) * weekend * growth * (0.8 + rand() * 0.4);
    // Pic de mise à jour : dix jours avant la fin, deux jours de forte affluence.
    const age = (to - t) / DAY;
    if (age > 9 && age < 11) w *= 2.1;
    // Tranche en cours : partielle.
    if (t + step > now) w *= (now - t) / step;
    const visitors = Math.round(base * w);
    const views = Math.round(visitors * (path && page?.path === path ? 1.25 : 2.6 + rand() * 0.6));
    series.push({ t, visitors, views });
  }

  const views = series.reduce((s, p) => s + p.views, 0);
  // Les visiteurs d'une tranche à l'autre se recoupent : le total est moindre que la somme.
  const visitors = Math.round(series.reduce((s, p) => s + p.visitors, 0) * (bucket === 'hour' ? 0.55 : 0.72));
  const duration = page?.durationS ?? 118;
  const totals = totalsFor(visitors, views, rand, duration);
  const prevFactor = 0.78 + rand() * 0.3;
  const previous = totalsFor(Math.round(visitors * prevFactor), Math.round(views * (prevFactor - 0.04)), rand, duration * 0.94);

  const listed = path ? PAGES.filter(p => p.path === path || (path !== '/' && p.path.startsWith(`${path}/`))) : PAGES;
  const listedWeight = listed.reduce((s, p) => s + p.weight, 0) || 1;
  const pages = listed
    .map(p => {
      const f = listed.length === 1 ? 1 : (p.weight / listedWeight) * (0.9 + rand() * 0.2);
      return {
        key: p.path,
        views: Math.round(views * f),
        visitors: Math.round(visitors * f * (listed.length === 1 ? 1 : 0.8)),
        avgDurationMs: Math.round(p.durationS * (0.85 + rand() * 0.3) * 1000),
      };
    })
    .sort((a, b) => b.views - a.views);

  const sectionMap = new Map<string, Count>();
  for (const p of pages) {
    const key = p.key === '/' ? '/' : `/${p.key.split('/')[1]}`;
    const c = sectionMap.get(key) ?? { key, visitors: 0, views: 0 };
    c.visitors += p.visitors; c.views += p.views;
    sectionMap.set(key, c);
  }
  const sections = [...sectionMap.values()].sort((a, b) => b.views - a.views);
  const entries = pages
    .map(p => ({ key: p.key, visitors: Math.round(p.visitors * (p.key === '/' ? 0.9 : p.key.startsWith('/lorebook/') ? 0.7 : 0.45)), views: 0 }))
    .map(c => ({ ...c, views: Math.round(c.visitors * 1.2) }))
    .sort((a, b) => b.visitors - a.visitors);

  return {
    range, path, from, to, bucket, totals, previous, series, pages, sections, entries,
    referrers: split(REFERRERS, visitors, views, rand),
    devices: split(DEVICES, visitors, views, rand),
    browsers: split(BROWSERS, visitors, views, rand),
    os: split(OS, visitors, views, rand),
    langs: split(LANGS, visitors, views, rand),
  };
}

/** Faux flux du direct : une marche aléatoire par page, un instantané toutes les 2 s. */
export function mockLive(onSnapshot: (s: LiveSnapshot) => void): () => void {
  const rand = rng(Date.now() & 0xffff);
  const current = new Map<string, number>();
  for (const p of PAGES) {
    const n = Math.round((p.weight / PAGE_WEIGHT) * 46 * (0.6 + rand() * 0.8));
    if (n > 0) current.set(p.path, n);
  }
  const tick = () => {
    for (const p of PAGES) {
      const n = current.get(p.path) ?? 0;
      const target = (p.weight / PAGE_WEIGHT) * 46;
      const r = rand();
      let next = n;
      if (r < 0.2) next = n + 1;
      else if (r < 0.38 && n > 1) next = n - 1;
      else if (r < 0.4 && n === 1) next = 0;
      // Rappel vers la fréquentation habituelle de la page.
      if (n > target * 2 && rand() < 0.4) next = n - 1;
      if (n === 0 && rand() < target / 6) next = 1;
      if (next > 0) current.set(p.path, next); else current.delete(p.path);
    }
    const pages = [...current].map(([path, visitors]) => ({ path, visitors })).sort((a, b) => b.visitors - a.visitors);
    onSnapshot({ t: Date.now(), total: pages.reduce((s, p) => s + p.visitors, 0), pages });
  };
  tick();
  const id = setInterval(tick, 2000);
  return () => clearInterval(id);
}

const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

export const mockSource: StatsSource = {
  me: async () => true,
  login: async () => true,
  logout: async () => {},
  async stats(range, path) {
    await delay(350);
    return mockStats(range, path);
  },
  live({ onSnapshot, onStatus }) {
    onStatus('open');
    return mockLive(onSnapshot);
  },
};
