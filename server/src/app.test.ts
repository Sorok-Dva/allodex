import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { LiveSnapshot, StatsResponse, TalentStatsResponse } from '../../src/analytics/api.ts';
import { eq } from 'drizzle-orm';
import { openDb, type DB } from './db.ts';
import { kv, pageviews, talentBuildEvents, talentBuilds } from './schema.ts';
import { createApp } from './app.ts';
import type { Config } from './config.ts';
import { measuredPath, referrerOf } from './analytics/collect.ts';
import { dayKey, dayStart, daysBetween } from './analytics/time.ts';
import { rangeBounds } from './analytics/stats.ts';
import { describe as describeBody, plain } from './seo/lore.ts';
import { buildId } from './talents/builds.ts';

const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

// Un dist/ minimal : index.html avec son bloc SEO et un Lorebook de deux entrées.
const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'allodex-dist-'));
const write = (rel: string, data: unknown) => {
  const file = path.join(dist, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, typeof data === 'string' ? data : JSON.stringify(data));
};
write('og/talents.jpg', 'jpg');
write('index.html', '<!doctype html><html lang="fr"><head><!--seo--><title>x</title><!--/seo--></head><body><div id="root"></div></body></html>');
for (const lang of ['en', 'fr', 'ru']) {
  write(`game/lorebook/list/${lang}/atlas.json`, { groups: [], rows: [['a-a003', 0, 0, 0, lang === 'fr' ? 'Île de Delice' : 'Delice Isle', 'Story allod']] });
}
write('game/lorebook/list/en/characters.json', { groups: [], rows: [['r425694', 0, 0, 0, '"Butcher"', 'Clone']] });
write('game/lorebook/text/en/atlas-0.json', { 'a-a003': { t: [], s: 'Story allod', f: [['climate', 'Temperate'], ['size', 'Medium island']] } });
// Talents : une version, une classe au livre d'une couche (un sort à trois rangs), sans grille.
write('game/talents/index.json', { versions: [{ id: '17.0', label: '17.0', client: '', languages: ['en'], format: 'v2', points: { book: 82, field: 77 },
  classes: [{ code: 'WARRIOR', slug: 'warrior', name: { en: 'Warrior' }, talents: 1, layers: 1, fields: 0, systems: [], missingNames: 0 }] }] });
write('game/talents/ui/talent_builder.json', { layout: { rankCost: [1, 2, 3] } });
write('game/talents/17.0/warrior.json', {
  version: '17.0', code: 'WARRIOR', ref: '#1', name: { en: 'Warrior' }, languages: ['en'], format: 'v2', fields: [],
  book: { ref: '#2', layers: [{ points: 0, cells: [{ type: 'TalentSpell', talent: 's1' }, null, null, null] }] },
  talents: { s1: { kind: 'spell', ref: 's1', name: {}, ranks: [{ ref: 'a' }, { ref: 'b' }, { ref: 'c' }] } },
});
write('game/lorebook/text/en/characters-0.json', { r425694: { t: [['bio', '## Butcher\n\nA **clone** built by the System of Total Annihilation.', 0]] } });

// Base MySQL jetable, vidée avant chaque test. Par défaut, le conteneur de développement :
//   docker run -d --name allodex-mysql-test -p 127.0.0.1:33406:3306 -e MYSQL_ROOT_PASSWORD=allodex \
//     -e MYSQL_DATABASE=allodex_test --tmpfs /var/lib/mysql mysql:8.4
const TEST_DATABASE_URL = process.env.TEST_DATABASE_URL ?? 'mysql://root:allodex@127.0.0.1:33406/allodex_test';
let db: DB;
let closeDb: () => Promise<void>;
beforeAll(async () => {
  try {
    ({ db, close: closeDb } = await openDb(TEST_DATABASE_URL));
  } catch (err) {
    throw new Error(`Base de test injoignable (${TEST_DATABASE_URL}) : voir la commande docker en tête de app.test.ts\n${err}`);
  }
});
afterAll(async () => {
  await closeDb?.();
  fs.rmSync(dist, { recursive: true, force: true });
});

const baseConfig: Config = {
  port: 0, host: '127.0.0.1', siteUrl: 'https://allodex.eu', databaseUrl: TEST_DATABASE_URL, distDir: dist,
  adminPassword: 'secret', sessionSecret: 'test', serveStatic: false, ownHosts: ['allodex.eu', 'localhost'], retentionDays: 395,
};

let clock: number;
let server: Awaited<ReturnType<typeof createApp>>;

beforeEach(async () => {
  await db.delete(pageviews);
  await db.delete(kv);
  await db.delete(talentBuildEvents);
  await db.delete(talentBuilds);
  clock = Date.UTC(2026, 8, 23, 10, 0, 0);
  server = await createApp(baseConfig, db, () => clock);
});

const request = (url: string, init: RequestInit = {}) => server.app.request(`http://localhost${url}`, init);

function collect(event: object, ua = CHROME, ip = '203.0.113.7') {
  return request('/api/collect', { method: 'POST', body: JSON.stringify(event), headers: { 'user-agent': ua, 'x-forwarded-for': ip, 'content-type': 'text/plain' } });
}

async function login() {
  const res = await request('/api/admin/login', { method: 'POST', body: JSON.stringify({ password: 'secret' }), headers: { 'content-type': 'application/json' } });
  expect(res.status).toBe(204);
  return res.headers.get('set-cookie')!.split(';')[0];
}

async function stats(query = 'range=24h') {
  const cookie = await login();
  const res = await request(`/api/admin/stats?${query}`, { headers: { cookie } });
  expect(res.status).toBe(200);
  return res.json() as Promise<StatsResponse>;
}

describe('collecte', () => {
  it('enregistre les vues, les sessions et la provenance de la première page', async () => {
    expect((await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/talents?b=xyz', referrer: 'https://www.google.fr/search?q=allods', lang: 'fr', width: 1920 })).status).toBe(204);
    clock += 30_000;
    await collect({ type: 'ping', session: 'sessionAAAA', view: 'view000001', path: '/talents', duration: 30_000 });
    await collect({ type: 'leave', session: 'sessionAAAA', view: 'view000001', path: '/talents', duration: 42_000 });
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000002', path: '/lorebook/atlas/a-a003', referrer: 'https://www.google.fr/', lang: 'fr' });
    await collect({ type: 'view', session: 'sessionBBBB', view: 'view000003', path: '/succes', lang: 'en' }, IPHONE, '198.51.100.2');

    const s = await stats();
    expect(s.totals).toMatchObject({ views: 3, visitors: 2, sessions: 2, bounceRate: 0.5 });
    expect(s.pages.find(p => p.key === '/talents')).toMatchObject({ views: 1, avgDurationMs: 42_000 });
    // L'alias /succes est compté sur /achievements ; la requête disparaît du chemin.
    expect(s.pages.map(p => p.key).sort()).toEqual(['/achievements', '/lorebook/atlas/a-a003', '/talents']);
    expect(s.sections.find(x => x.key === '/lorebook')?.views).toBe(1);
    expect(s.entries.map(e => e.key).sort()).toEqual(['/achievements', '/talents']);
    expect(s.referrers).toEqual(expect.arrayContaining([{ key: 'google.com', visitors: 1, views: 1 }, { key: '(direct)', visitors: 1, views: 1 }]));
    expect(s.devices.map(d => d.key).sort()).toEqual(['desktop', 'mobile']);
    expect(s.browsers.map(d => d.key).sort()).toEqual(['Chrome', 'Safari']);
    expect(s.series).toHaveLength(24);
    expect(s.series.at(-1)!.views).toBe(3);
  });

  it('ignore les robots et refuse les événements mal formés', async () => {
    expect((await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/' }, 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)')).status).toBe(204);
    expect((await collect({ type: 'view', session: 'x', view: 'view000001', path: '/' })).status).toBe(400);
    expect((await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: 'https://evil.example/' })).status).toBe(400);
    expect((await request('/api/collect', { method: 'POST', body: '{', headers: { 'user-agent': CHROME } })).status).toBe(400);
    expect((await stats()).totals.views).toBe(0);
  });

  it('ne mesure pas le tableau de bord lui-même', async () => {
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/stats' });
    expect((await stats()).totals.views).toBe(0);
  });

  it('filtre par chemin', async () => {
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/talents' });
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000002', path: '/music' });
    const s = await stats('range=7d&path=/talents');
    expect(s.path).toBe('/talents');
    expect(s.totals.views).toBe(1);
    expect(s.pages.map(p => p.key)).toEqual(['/talents']);
    expect(s.bucket).toBe('day');
    expect(s.series).toHaveLength(7);
  });

  it('étend le filtre aux sous-pages, sans confondre les caractères spéciaux', async () => {
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/lorebook' });
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000002', path: '/lorebook/atlas/a_1' });
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000003', path: '/lorebookx/y' });
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000004', path: '/' });
    expect((await stats('range=24h&path=/lorebook')).totals.views).toBe(2);
    // `_` est un joker de LIKE : `/lorebook_` ne doit pas englober `/lorebookx/y`.
    expect((await stats('range=24h&path=/lorebook_')).totals.views).toBe(0);
    expect((await stats('range=24h&path=/')).totals.views).toBe(1);
  });
});

describe('builds de talents', () => {
  const event = (body: object, ua = CHROME, ip = '203.0.113.7') =>
    request('/api/talents/events', { method: 'POST', body: JSON.stringify(body), headers: { 'user-agent': ua, 'x-forwarded-for': ip, 'content-type': 'text/plain' } });
  async function talentStats(range = '24h') {
    const cookie = await login();
    const res = await request(`/api/admin/talents?range=${range}`, { headers: { cookie } });
    expect(res.status).toBe(200);
    return res.json() as Promise<TalentStatsResponse>;
  }

  it('enregistre les builds composés, partagés et vus, une fois par visiteur et par jour', async () => {
    const build = { v: '17.0', c: 'warrior', b: '1.2' };
    expect((await event({ kind: 'generate', ...build })).status).toBe(204);
    await event({ kind: 'generate', ...build });
    await event({ kind: 'share', ...build });
    // L'auteur qui rouvre son build le jour même n'ajoute pas de vue ; les autres, si.
    await event({ kind: 'view', ...build });
    await event({ kind: 'view', ...build }, IPHONE, '198.51.100.2');
    await event({ kind: 'view', ...build }, IPHONE, '198.51.100.2');
    await event({ kind: 'view', ...build }, CHROME, '198.51.100.3');
    await event({ kind: 'generate', v: '17.0', c: 'warrior', b: '1.3', b2: '1.2' });

    const [row] = await db.select().from(talentBuilds).where(eq(talentBuilds.id, buildId('17.0', 'warrior', '1.2', null)));
    expect(row).toMatchObject({ version: '17.0', cls: 'warrior', b: '1.2', b2: null, generations: 1, shares: 1, views: 2, playerId: null });

    const s = await talentStats();
    expect(s.totals).toEqual({ builds: 2, generations: 2, shares: 1, views: 2 });
    expect(s.allTime).toEqual({ builds: 2, generations: 2, shares: 1, views: 2 });
    expect(s.classes).toEqual([{ version: '17.0', cls: 'warrior', builds: 2, generations: 2, shares: 1, views: 2 }]);
    expect(s.top[0]).toMatchObject({ b: '1.2', period: { generations: 1, shares: 1, views: 2 }, total: { views: 2 } });
    expect(s.top).toHaveLength(2);

    // Le lendemain, le même visiteur compte de nouveau ; la période de 24 h n'a plus que ce jour-là.
    clock += 24 * 3_600_000;
    await event({ kind: 'view', ...build }, IPHONE, '198.51.100.2');
    expect((await talentStats()).totals).toEqual({ builds: 0, generations: 0, shares: 0, views: 1 });
    expect((await talentStats('7d')).allTime.views).toBe(3);
  });

  it('refuse les builds invalides et ignore les robots', async () => {
    expect((await event({ kind: 'generate', v: '17.0', c: 'warrior', b: '1.4' })).status).toBe(400);   // rang > 3
    expect((await event({ kind: 'generate', v: '17.0', c: 'warrior', b: '1.0' })).status).toBe(400);   // sous le rang de départ
    expect((await event({ kind: 'generate', v: '17.0', c: 'mage', b: '1.2' })).status).toBe(400);
    expect((await event({ kind: 'generate', v: '../..', c: 'warrior', b: '1.2' })).status).toBe(400);
    expect((await event({ kind: 'generate', v: '17.0', c: 'warrior' })).status).toBe(400);
    expect((await event({ kind: 'like', v: '17.0', c: 'warrior', b: '1.2' })).status).toBe(400);
    expect((await event({ kind: 'generate', v: '17.0', c: 'warrior', b: '1.2' }, 'Mozilla/5.0 (compatible; Googlebot/2.1)')).status).toBe(204);
    expect(await db.select().from(talentBuilds)).toHaveLength(0);
    expect((await request('/api/admin/talents')).status).toBe(401);
  });
});

describe('direct', () => {
  it('compte les visiteurs par page et retire ceux qui partent ou se taisent', async () => {
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000001', path: '/talents' });
    await collect({ type: 'view', session: 'sessionBBBB', view: 'view000002', path: '/talents' }, IPHONE, '198.51.100.2');
    await collect({ type: 'view', session: 'sessionCCCC', view: 'view000003', path: '/music' }, CHROME, '198.51.100.3');
    let snap: LiveSnapshot = server.live.snapshot(clock);
    expect(snap.total).toBe(3);
    expect(snap.pages).toEqual([{ path: '/talents', visitors: 2 }, { path: '/music', visitors: 1 }]);

    // Le `leave` d'une vue déjà remplacée ne retire pas l'onglet.
    await collect({ type: 'view', session: 'sessionAAAA', view: 'view000004', path: '/music' });
    await collect({ type: 'leave', session: 'sessionAAAA', view: 'view000001', path: '/talents' });
    snap = server.live.snapshot(clock);
    expect(snap.pages).toEqual([{ path: '/music', visitors: 2 }, { path: '/talents', visitors: 1 }]);

    await collect({ type: 'leave', session: 'sessionCCCC', view: 'view000003', path: '/music' }, CHROME, '198.51.100.3');
    clock += 60_000;
    await collect({ type: 'ping', session: 'sessionAAAA', view: 'view000004', path: '/music' });
    expect(server.live.snapshot(clock)).toEqual({ t: clock, total: 1, pages: [{ path: '/music', visitors: 1 }] });
  });
});

describe('administration', () => {
  it('protège les statistiques par mot de passe', async () => {
    expect((await request('/api/admin/stats')).status).toBe(401);
    expect((await request('/api/admin/me')).status).toBe(401);
    const wrong = await request('/api/admin/login', { method: 'POST', body: JSON.stringify({ password: 'nope' }), headers: { 'content-type': 'application/json' } });
    expect(wrong.status).toBe(401);
    const cookie = await login();
    expect((await request('/api/admin/me', { headers: { cookie } })).status).toBe(204);
    expect((await request('/api/admin/me', { headers: { cookie: `${cookie}x` } })).status).toBe(401);
    clock += 31 * 24 * 3_600_000;
    expect((await request('/api/admin/me', { headers: { cookie } })).status).toBe(401);
  });

  it('bloque le mot de passe après trop d’échecs, toutes IP confondues', async () => {
    for (let i = 0; i < 20; i++) {
      const res = await request('/api/admin/login', { method: 'POST', body: JSON.stringify({ password: 'nope' }), headers: { 'x-real-ip': `192.0.2.${i}` } });
      expect(res.status).toBe(401);
    }
    const blocked = await request('/api/admin/login', { method: 'POST', body: JSON.stringify({ password: 'secret' }), headers: { 'x-real-ip': '192.0.2.99' } });
    expect(blocked.status).toBe(429);
    clock += 3_600_001;
    await login();
  });

  it("désactive l'administration sans mot de passe configuré", async () => {
    const open = await createApp({ ...baseConfig, adminPassword: '' }, db, () => clock);
    const res = await open.app.request('http://localhost/api/admin/login', { method: 'POST', body: JSON.stringify({ password: '' }) });
    expect(res.status).toBe(503);
    expect((await open.app.request('http://localhost/api/admin/stats')).status).toBe(401);
  });
});

describe('pages', () => {
  const page = async (url: string, headers: Record<string, string> = {}) => {
    const res = await request(url, { headers });
    return { status: res.status, html: await res.text() };
  };

  it('écrit le titre, la description, la canonique et Open Graph de chaque page', async () => {
    const { status, html } = await page('/talents');
    expect(status).toBe(200);
    expect(html).toContain('<title>Calculateur de talents Allods Online (1.1 à 17.0) — Allodex</title>');
    expect(html).toContain('<link rel="canonical" href="https://allodex.eu/talents" />');
    expect(html).toContain('<meta property="og:image" content="https://allodex.eu/og/talents.jpg" />');
    expect(html).toContain('hreflang="en" href="https://allodex.eu/talents?lang=en"');
    expect(html).not.toContain('<title>x</title>');
    // Pas encore d'image propre à la page : l'image générique.
    expect((await page('/music')).html).toContain('content="https://allodex.eu/og/default.jpg"');
  });

  it("suit la langue demandée, puis celle du navigateur", async () => {
    expect((await page('/talents?lang=en')).html).toContain('<html lang="en"');
    expect((await page('/talents?lang=en')).html).toContain('href="https://allodex.eu/talents?lang=en" />\n');
    expect((await page('/music', { 'accept-language': 'en-GB,en;q=0.9' })).html).toContain('Allods Online soundtrack');
  });

  it("décrit les entrées du Lorebook à partir de leur texte", async () => {
    const { status, html } = await page('/lorebook/characters/r425694');
    expect(status).toBe(200);
    expect(html).toContain('<title>&quot;Butcher&quot; — Characters · Allods Online Lorebook</title>');
    expect(html).toContain('content="Butcher A clone built by the System of Total Annihilation."');
    expect(html).toContain('"@type":"Article"');
    const atlas = await page('/lorebook/atlas/a-a003?text=fr');
    expect(atlas.html).toContain('<title>Île de Delice — Atlas · Allods Online Lorebook</title>');
    // Pas de texte : sous-titre et caractéristiques (texte anglais en repli).
    expect(atlas.html).toContain('content="Story allod · Temperate · Medium island"');
    expect(atlas.html).toContain('<html lang="fr"');
  });

  it('répond 404 aux chemins et entrées inconnus', async () => {
    expect((await page('/nope')).status).toBe(404);
    const missing = await page('/lorebook/atlas/zzz');
    expect(missing.status).toBe(404);
    expect(missing.html).toContain('noindex');
    expect((await page('/stats')).html).toContain('content="noindex,nofollow"');
  });

  it('publie robots.txt et le plan du site', async () => {
    const robots = await (await request('/robots.txt')).text();
    expect(robots).toContain('Sitemap: https://allodex.eu/sitemap.xml');
    const index = await (await request('/sitemap.xml')).text();
    expect(index).toContain('<loc>https://allodex.eu/sitemaps/pages.xml</loc>');
    expect(index).toContain('<loc>https://allodex.eu/sitemaps/lorebook-atlas.xml</loc>');
    const atlas = await (await request('/sitemaps/lorebook-atlas.xml')).text();
    expect(atlas).toContain('<loc>https://allodex.eu/lorebook/atlas/a-a003?text=ru</loc>');
    expect(atlas.match(/<url>/g)).toHaveLength(3);
    const pages = await (await request('/sitemaps/pages.xml')).text();
    expect(pages).toContain('<loc>https://allodex.eu/cinematics?lang=en</loc>');
    expect(pages).not.toContain('/stats');
    expect((await request('/sitemaps/nope.xml')).status).toBe(404);
  });
});

describe('outils', () => {
  it('normalise les chemins et les provenances', () => {
    expect(measuredPath('/lorebook/atlas/a%20b?x=1#y')).toBe('/lorebook/atlas/a%20b');
    expect(measuredPath('/chroniques/')).toBe('/chronicles');
    expect(measuredPath('talents')).toBeNull();
    expect(referrerOf('https://allodex.eu/talents', ['allodex.eu'])).toBeNull();
    expect(referrerOf('https://www.google.co.uk/', [])).toBe('google.com');
    expect(referrerOf('https://discord.com/channels/1', [])).toBe('discord.com');
    expect(referrerOf('Newsletter', [])).toBe('newsletter');
  });

  it("découpe les jours à l'heure de Paris, changements d'heure compris", () => {
    const octoberSwitch = Date.UTC(2026, 9, 25, 12);
    expect(dayKey(dayStart(octoberSwitch))).toBe('2026-10-25');
    expect(dayStart(octoberSwitch)).toBe(Date.UTC(2026, 9, 24, 22));
    const days = daysBetween(Date.UTC(2026, 9, 24, 22), Date.UTC(2026, 9, 27, 12));
    expect(days.map(d => d.key)).toEqual(['2026-10-25', '2026-10-26', '2026-10-27']);
    expect(days[1].t).toBe(Date.UTC(2026, 9, 25, 23));
    const week = rangeBounds('7d', Date.UTC(2026, 8, 23, 10));
    expect(daysBetween(week.from, week.to)).toHaveLength(7);
  });

  it('résume le texte des entrées', () => {
    expect(plain('## Titre\n\n- **gras** et *italique* [lien](https://x)')).toBe('Titre gras et italique lien');
    expect(describeBody({ t: [['a', 0, 0], ['b', 'Texte.', 0]] })).toBe('Texte.');
    expect(describeBody({ t: [], i: [{ t: [['a', 'Étape une.', 0]] }] })).toBe('Étape une.');
  });
});
