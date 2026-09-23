import { describe, expect, it } from 'vitest';
import {
  formatCount, formatDuration, formatPercent, formatTrend, niceTicks, parseScreenQuery, pathLabel,
  referrerLabel, screenUrl, statsRequestUrl, timeTicks, trend,
} from './format';
import { mockStats } from './mock';

/** Les formats français emploient des espaces insécables (fines ou non) : on les normalise. */
const plain = (v: string) => v.replace(/[  ]/g, ' ');

describe('formats des statistiques', () => {
  it('formate les durées en secondes, minutes et heures', () => {
    expect(plain(formatDuration(0))).toBe('0 s');
    expect(plain(formatDuration(42_400))).toBe('42 s');
    expect(plain(formatDuration(185_000))).toBe('3 min 05 s');
    expect(plain(formatDuration(4_320_000))).toBe('1 h 12 min');
    expect(formatDuration(Number.NaN)).toBe('—');
  });
  it('formate pourcentages et comptes à la française', () => {
    expect(plain(formatPercent(0.382))).toBe('38 %');
    expect(plain(formatPercent(0.382, 1))).toBe('38,2 %');
    expect(plain(formatPercent(0.045))).toBe('4,5 %');
    expect(plain(formatCount(12345))).toBe('12 345');
    expect(plain(formatCount(1_234_567))).toBe('1,2 M');
  });
  it('lit les évolutions, le rebond à l’envers', () => {
    expect(trend(120, 100)).toMatchObject({ direction: 'up', tone: 'good' });
    expect(trend(80, 100)).toMatchObject({ direction: 'down', tone: 'bad' });
    expect(trend(0.3, 0.4, true)).toMatchObject({ direction: 'down', tone: 'good' });
    expect(trend(0.5, 0.4, true)).toMatchObject({ direction: 'up', tone: 'bad' });
    expect(trend(1002, 1000)).toMatchObject({ direction: 'flat', tone: 'neutral' });
    expect(trend(5, 0)).toMatchObject({ ratio: null, tone: 'neutral' });
    expect(plain(formatTrend(trend(112, 100)))).toBe('+12 %');
    expect(plain(formatTrend(trend(96.6, 100)))).toBe('−3,4 %');
    expect(formatTrend(trend(1000, 1000))).toBe('stable');
    expect(formatTrend(trend(5, 0))).toBe('nouveau');
  });
});

describe('libellés des chemins', () => {
  it('nomme les rubriques et garde les chemins du Lorebook', () => {
    expect(pathLabel('/')).toEqual({ label: 'Accueil', detail: null });
    expect(pathLabel('/talents')).toEqual({ label: 'Talents', detail: '/talents' });
    expect(pathLabel('/achievements').label).toBe('Succès');
    expect(pathLabel('/chronicles').label).toBe('Chroniques');
    expect(pathLabel('/music').label).toBe('Musiques');
    expect(pathLabel('/cinematics').label).toBe('Cinématiques');
    expect(pathLabel('/lorebook').label).toBe('Lorebook');
    expect(pathLabel('/terms').label).toBe('CGU');
    expect(pathLabel('/lorebook/characters/r425694')).toEqual({ label: '/lorebook/characters/r425694', detail: null });
    expect(referrerLabel('(direct)')).toBe('Accès direct');
    expect(referrerLabel('google.com')).toBe('google.com');
  });
});

describe('adresses', () => {
  it('construit la requête de l’API', () => {
    expect(statsRequestUrl('7d', null)).toBe('/api/admin/stats?range=7d');
    expect(statsRequestUrl('30d', '/talents')).toBe('/api/admin/stats?range=30d&path=%2Ftalents');
  });
  it('lit et réécrit l’URL partageable de l’écran', () => {
    const q = parseScreenQuery(new URLSearchParams('range=30d&path=/talents'));
    expect(q).toEqual({ range: '30d', path: '/talents', mock: false });
    expect(screenUrl(q)).toBe('/stats?range=30d&path=/talents');
    expect(screenUrl({ range: '24h', path: '/lorebook/characters/r1 x', mock: true })).toBe('/stats?range=24h&path=/lorebook/characters/r1%20x&mock');
    expect(parseScreenQuery(new URLSearchParams('range=2y&path=talents'))).toEqual({ range: '7d', path: null, mock: false });
    expect(parseScreenQuery(new URLSearchParams('mock')).mock).toBe(true);
  });
});

describe('graduations', () => {
  it('arrondit l’axe des comptes', () => {
    expect(niceTicks(100)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(3)).toEqual([0, 1, 2, 3]);
    expect(niceTicks(0)).toEqual([0, 1]);
    const t = niceTicks(1234);
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(1234);
  });
  it('gradue le temps en heures de Paris', () => {
    // 23 sept. 2026, 0 h à Paris = 22 h UTC la veille (heure d’été).
    const start = Date.UTC(2026, 8, 22, 22);
    const series = Array.from({ length: 24 }, (_, i) => ({ t: start + i * 3_600_000 }));
    const ticks = timeTicks(series, 'hour', 10);
    expect(ticks.map(t => t.index)).toEqual([0, 3, 6, 9, 12, 15, 18, 21]);
    expect(plain(ticks[1].label)).toBe('3 h');
    expect(ticks[0].label).toMatch(/23/);
    expect(timeTicks(series, 'hour', 3).length).toBeLessThanOrEqual(3);
  });
});

describe('maquette', () => {
  it('respecte la forme du contrat', () => {
    const now = Date.UTC(2026, 8, 23, 12);
    const r = mockStats('7d', null, now);
    expect(r.bucket).toBe('hour');
    expect(r.series).toHaveLength(7 * 24);
    expect(r.to - r.from).toBe(7 * 86_400_000);
    expect(r.pages.length).toBeGreaterThanOrEqual(15);
    expect(r.referrers.map(c => c.key)).toContain('(direct)');
    const filtered = mockStats('30d', '/talents', now);
    expect(filtered.path).toBe('/talents');
    expect(filtered.pages.map(p => p.key)).toEqual(['/talents']);
    expect(filtered.totals.views).toBeLessThan(mockStats('30d', null, now).totals.views);
  });
});
