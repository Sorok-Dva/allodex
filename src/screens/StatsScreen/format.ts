/**
 * Logique pure du tableau de bord d'audience : formats français, libellés des chemins,
 * URL de requête et de partage, graduations des graphiques.
 */
import { RANGES, type Range } from '@/analytics/api';

export const DEFAULT_RANGE: Range = '7d';
export const TIME_ZONE = 'Europe/Paris';

/** `tiny` et `previousTiny` : variantes pour les écrans de téléphone. */
export const RANGE_LABELS: Record<Range, { short: string; tiny: string; long: string; previous: string; previousTiny: string }> = {
  '24h': { short: '24 h', tiny: '24 h', long: 'les dernières 24 heures', previous: 'les 24 h précédentes', previousTiny: '24 h préc.' },
  '7d': { short: '7 jours', tiny: '7 j', long: 'les 7 derniers jours', previous: 'les 7 jours précédents', previousTiny: '7 j préc.' },
  '30d': { short: '30 jours', tiny: '30 j', long: 'les 30 derniers jours', previous: 'les 30 jours précédents', previousTiny: '30 j préc.' },
  '90d': { short: '90 jours', tiny: '90 j', long: 'les 90 derniers jours', previous: 'les 90 jours précédents', previousTiny: '90 j préc.' },
  '12m': { short: '12 mois', tiny: '1 an', long: 'les 12 derniers mois', previous: 'les 12 mois précédents', previousTiny: '12 mois préc.' },
};

export const isRange = (v: string | null): v is Range => v !== null && (RANGES as readonly string[]).includes(v);

// --- nombres -------------------------------------------------------------------------------

const intFmt = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const compactFmt = new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 });
const oneDecimal = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** 12 345 en entier ; au-delà de 100 000, forme compacte (123 k, 1,2 M). */
export function formatCount(n: number): string {
  if (!Number.isFinite(n)) return '—';
  return Math.abs(n) >= 100_000 ? compactFmt.format(n) : intFmt.format(Math.round(n));
}

/** Nombre à une décimale (pages par session : « 2,4 »). */
export const formatDecimal = (n: number) => (Number.isFinite(n) ? oneDecimal.format(n) : '—');

/**
 * Part entre 0 et 1 en pourcentage français (« 38,2 % », espace fine insécable).
 * Une décimale sous 10 %, aucune au-delà sauf demande.
 */
export function formatPercent(ratio: number, digits?: number): string {
  if (!Number.isFinite(ratio)) return '—';
  const pct = ratio * 100;
  const d = digits ?? (Math.abs(pct) < 10 && pct !== 0 ? 1 : 0);
  return `${new Intl.NumberFormat('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }).format(pct)} %`;
}

/** Durée lisible : « 42 s », « 3 min 05 s », « 1 h 12 min ». */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total} s`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h} h ${String(m).padStart(2, '0')} min`;
  return `${m} min ${String(s).padStart(2, '0')} s`;
}

// --- évolutions ----------------------------------------------------------------------------

export type Trend = {
  /** Variation relative (0,12 = +12 %), `null` quand la période précédente est vide. */
  ratio: number | null;
  direction: 'up' | 'down' | 'flat';
  /** Lecture de la variation : `good`, `bad` ou `neutral` (stable, ou sans référence). */
  tone: 'good' | 'bad' | 'neutral';
};

/** Seuil sous lequel une variation est dite stable (0,5 %). */
const FLAT = 0.005;

/**
 * Évolution de `current` par rapport à `previous`. `lowerIsBetter` inverse la lecture :
 * pour le taux de rebond, une baisse est une bonne nouvelle.
 */
export function trend(current: number, previous: number, lowerIsBetter = false): Trend {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous <= 0) {
    return { ratio: null, direction: current > 0 ? 'up' : 'flat', tone: 'neutral' };
  }
  const ratio = (current - previous) / previous;
  if (Math.abs(ratio) < FLAT) return { ratio, direction: 'flat', tone: 'neutral' };
  const direction = ratio > 0 ? 'up' : 'down';
  const good = lowerIsBetter ? direction === 'down' : direction === 'up';
  return { ratio, direction, tone: good ? 'good' : 'bad' };
}

/** « +12 % », « −3,4 % », « stable », « nouveau ». */
export function formatTrend(t: Trend): string {
  if (t.ratio === null) return t.direction === 'up' ? 'nouveau' : '—';
  if (t.direction === 'flat') return 'stable';
  const sign = t.ratio > 0 ? '+' : '−';
  return `${sign}${formatPercent(Math.abs(t.ratio))}`;
}

// --- libellés -------------------------------------------------------------------------------

/** Rubriques du site et leurs alias d'URL (voir `src/App.tsx`). */
const SECTIONS: [string[], string][] = [
  [['/'], 'Accueil'],
  [['/achievements', '/medals', '/succes'], 'Succès'],
  [['/chronicles', '/chroniques'], 'Chroniques'],
  [['/music', '/musiques'], 'Musiques'],
  [['/cinematics', '/cinematiques'], 'Cinématiques'],
  [['/talents'], 'Talents'],
  [['/lorebook'], 'Lorebook'],
  [['/terms', '/cgu', '/legal'], 'CGU'],
  [['/fatalities', '/fatalites'], 'Fatalités'],
  [['/character', '/personnage'], 'Création de personnage'],
  [['/stats'], 'Statistiques'],
];
const SECTION_BY_PATH = new Map(SECTIONS.flatMap(([paths, label]) => paths.map(p => [p, label] as const)));

/** Nom de rubrique d'un chemin exact (`/talents` → « Talents »), ou null. */
export const sectionLabel = (path: string): string | null => SECTION_BY_PATH.get(path.replace(/\/+$/, '') || '/') ?? null;

/**
 * Libellé d'un chemin pour les classements : nom de la rubrique pour ses pages d'accueil,
 * chemin brut sinon (`/lorebook/characters/r425694` reste tel quel).
 */
export function pathLabel(path: string): { label: string; detail: string | null } {
  const section = sectionLabel(path);
  if (section) return { label: section, detail: path === '/' ? null : path };
  return { label: path, detail: null };
}

const DEVICE_LABELS: Record<string, string> = { desktop: 'Ordinateur', mobile: 'Mobile', tablet: 'Tablette' };
const LANG_LABELS: Record<string, string> = { fr: 'Français', en: 'Anglais', ru: 'Russe', de: 'Allemand' };

export const referrerLabel = (key: string) => (key === '(direct)' || key === '' ? 'Accès direct' : key);
export const deviceLabel = (key: string) => DEVICE_LABELS[key] ?? key;
export const langLabel = (key: string) => LANG_LABELS[key] ?? key.toUpperCase();

// --- URL -----------------------------------------------------------------------------------

/** `encodeURIComponent` qui laisse les `/` lisibles (autorisés dans une requête, RFC 3986). */
const encodePath = (p: string) => encodeURIComponent(p).replace(/%2F/gi, '/');

/** URL de l'API : `/api/admin/stats?range=30d&path=%2Ftalents`. */
export function statsRequestUrl(range: Range, path: string | null): string {
  const q = new URLSearchParams({ range });
  if (path) q.set('path', path);
  return `/api/admin/stats?${q}`;
}

export type ScreenQuery = { range: Range; path: string | null; mock: boolean };

/** Lit période, filtre et mode maquette dans la requête de `/stats`. */
export function parseScreenQuery(query: URLSearchParams): ScreenQuery {
  const range = query.get('range');
  const path = query.get('path');
  return {
    range: isRange(range) ? range : DEFAULT_RANGE,
    path: path && path.startsWith('/') ? path : null,
    mock: query.has('mock'),
  };
}

/** URL partageable de l'écran : `/stats?range=30d&path=/talents` (`mock` conservé en dev). */
export function screenUrl({ range, path, mock }: ScreenQuery): string {
  const parts = [`range=${range}`];
  if (path) parts.push(`path=${encodePath(path)}`);
  if (mock) parts.push('mock');
  return `/stats?${parts.join('&')}`;
}

// --- temps ---------------------------------------------------------------------------------

type Parts = { year: number; month: number; day: number; hour: number };
const partsFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TIME_ZONE, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', hourCycle: 'h23',
});
/** Année, mois (1-12), jour et heure à Paris. */
export function parisParts(t: number): Parts {
  const out: Parts = { year: 0, month: 0, day: 0, hour: 0 };
  for (const p of partsFmt.formatToParts(t)) {
    if (p.type === 'year' || p.type === 'month' || p.type === 'day' || p.type === 'hour') out[p.type] = Number(p.value);
  }
  return out;
}

const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('fr-FR', { timeZone: TIME_ZONE, ...o });
const dayShort = fmt({ weekday: 'short', day: 'numeric' });
const dayMonth = fmt({ day: 'numeric', month: 'short' });
const monthShort = fmt({ month: 'short' });
const monthYear = fmt({ month: 'short', year: 'numeric' });
const dayLong = fmt({ weekday: 'long', day: 'numeric', month: 'long' });
const dayLongYear = fmt({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const hourMinute = fmt({ hour: '2-digit', minute: '2-digit' });

export const formatClock = (t: number) => hourMinute.format(t);

export type Tick = { index: number; label: string };

/**
 * Graduations de l'axe du temps, en heure de Paris. Candidats selon la tranche et la
 * durée (toutes les 3 h, chaque minuit, chaque jour, chaque 1er du mois), puis un sur
 * `k` pour ne pas dépasser `maxTicks`.
 */
export function timeTicks(series: { t: number }[], bucket: 'hour' | 'day', maxTicks: number): Tick[] {
  if (series.length === 0) return [];
  const span = series[series.length - 1].t - series[0].t;
  const DAY = 86_400_000;
  const candidates: Tick[] = [];
  series.forEach(({ t }, index) => {
    const p = parisParts(t);
    if (bucket === 'hour') {
      if (span <= 1.5 * DAY) {
        if (p.hour % 3 === 0) candidates.push({ index, label: p.hour === 0 ? dayShort.format(t) : `${p.hour} h` });
      } else if (p.hour === 0) candidates.push({ index, label: dayShort.format(t) });
    } else if (span <= 100 * DAY) {
      candidates.push({ index, label: dayMonth.format(t).replace('.', '') });
    } else if (p.day === 1) {
      candidates.push({ index, label: (p.month === 1 ? monthYear : monthShort).format(t).replace('.', '') });
    }
  });
  const max = Math.max(1, maxTicks);
  if (candidates.length <= max) return candidates;
  const step = Math.ceil(candidates.length / max);
  // Garder le dernier candidat (le plus récent) et remonter de `step` en `step`.
  return candidates.filter((_, i) => (candidates.length - 1 - i) % step === 0);
}

/** Libellé complet d'une tranche pour l'infobulle : « mardi 23 septembre, 14 h – 15 h ». */
export function bucketLabel(t: number, bucket: 'hour' | 'day', withYear = false): string {
  const day = (withYear ? dayLongYear : dayLong).format(t);
  if (bucket === 'day') return day;
  const h = parisParts(t).hour;
  return `${day}, ${h} h – ${(h + 1) % 24} h`;
}

/** Graduations « rondes » de 0 à au moins `max` (1, 2, 2,5 ou 5 × 10ⁿ), `count` intervalles visés. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  // Des comptes : pas de pas fractionnaire (2,5 seulement à partir de 25).
  const step = Math.max(1, [1, 2, 2.5, 5, 10].map(m => m * pow).find(s => s >= raw && Number.isInteger(s)) ?? 10 * pow);
  const ticks: number[] = [];
  for (let i = 0; i * step < max + step * 0.999; i++) ticks.push(i * step);
  if (ticks.length < 2) ticks.push(step);
  return ticks;
}

/** « il y a 12 s », « il y a 3 min », « à 14:32 ». */
export function formatAgo(t: number, now: number): string {
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 5) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  return `à ${formatClock(t)}`;
}
