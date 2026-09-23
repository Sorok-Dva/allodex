import { Hono, type Context } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { streamSSE } from 'hono/streaming';
import { getConnInfo } from '@hono/node-server/conninfo';
import { serveStatic } from '@hono/node-server/serve-static';
import { RANGES, type Range } from '../../src/analytics/api.ts';
import type { Config } from './config.ts';
import type { DB } from './db.ts';
import { ADMIN_COOKIE, SESSION_TTL, createAuth } from './auth.ts';
import { Live } from './analytics/live.ts';
import { createCollector, createRateLimiter, measuredPath } from './analytics/collect.ts';
import { createStats } from './analytics/stats.ts';
import { createVisitorHasher } from './analytics/visitor.ts';
import { createLoreIndex } from './seo/lore.ts';
import { createPageRenderer } from './seo/pages.ts';
import { createSitemaps } from './seo/sitemap.ts';

const MAX_BODY = 8 * 1024;
const LIVE_INTERVAL = 2000;

const LOOPBACK = /^(127\.|::1$|::ffff:127\.)/;

/**
 * IP du visiteur. Les en-têtes de nginx (`X-Real-IP`, puis `X-Forwarded-For`, qu'il réécrit
 * avec la seule adresse du client) ne sont crus que si la connexion vient de la machine même :
 * un client joignant directement le port ne peut pas se faire passer pour un autre.
 */
function clientIp(c: Context): string {
  let remote = '';
  try { remote = getConnInfo(c).remote.address ?? ''; } catch { /* requête sans socket (tests) */ }
  if (remote && !LOOPBACK.test(remote)) return remote;
  return c.req.header('x-real-ip')?.trim() || c.req.header('x-forwarded-for')?.split(',')[0]?.trim() || remote;
}

const isHttps = (c: Context) => c.req.header('x-forwarded-proto') === 'https' || new URL(c.req.url).protocol === 'https:';

export async function createApp(config: Config, db: DB, now: () => number = Date.now) {
  const app = new Hono();
  const live = new Live();
  const collect = createCollector(db, live, createVisitorHasher(db), config.ownHosts);
  const stats = createStats(db);
  const auth = await createAuth(db, config.adminPassword, config.sessionSecret);
  const collectLimit = createRateLimiter(240);
  const loginLimit = createRateLimiter(8);
  // Mot de passe unique : plafond d'échecs toutes IP confondues, contre une attaque répartie.
  const failedLogins: number[] = [];
  const MAX_FAILED_PER_HOUR = 20;
  const lore = createLoreIndex(`${config.distDir}/game/lorebook`);
  const render = createPageRenderer(config.distDir, config.siteUrl, lore);
  const sitemaps = createSitemaps(config.siteUrl, lore);

  // --- mesure d'audience ---------------------------------------------------------------------------

  app.post('/api/collect', async c => {
    const ip = clientIp(c);
    if (!collectLimit(ip, now())) return c.body(null, 429);
    const text = await c.req.text();
    if (text.length > MAX_BODY) return c.body(null, 413);
    let payload: unknown;
    try { payload = JSON.parse(text); } catch { return c.body(null, 400); }
    const ctx = { ip, ua: c.req.header('user-agent') ?? '', now: now() };
    const events = Array.isArray(payload) ? payload.slice(0, 10) : [payload];
    const results = [];
    for (const ev of events) results.push(await collect(ev, ctx));
    return c.body(null, results.includes('invalid') && !results.includes('ok') ? 400 : 204);
  });

  // --- administration ------------------------------------------------------------------------------

  const isAdmin = (c: Context) => auth.verify(getCookie(c, ADMIN_COOKIE), now());

  app.post('/api/admin/login', async c => {
    if (!auth.enabled) return c.json({ error: 'disabled' }, 503);
    const t = now();
    while (failedLogins.length && t - failedLogins[0] > 3_600_000) failedLogins.shift();
    if (failedLogins.length >= MAX_FAILED_PER_HOUR || !loginLimit(clientIp(c), t)) return c.json({ error: 'rate' }, 429);
    const body = await c.req.json().catch(() => ({})) as { password?: unknown };
    if (!auth.checkPassword(body.password)) {
      failedLogins.push(t);
      return c.json({ error: 'password' }, 401);
    }
    setCookie(c, ADMIN_COOKIE, auth.issue(now()), {
      httpOnly: true, secure: isHttps(c), sameSite: 'Strict', path: '/api/admin', maxAge: SESSION_TTL / 1000,
    });
    return c.body(null, 204);
  });

  app.post('/api/admin/logout', c => {
    deleteCookie(c, ADMIN_COOKIE, { path: '/api/admin' });
    return c.body(null, 204);
  });

  app.use('/api/admin/*', async (c, next) => {
    if (c.req.path === '/api/admin/login' || c.req.path === '/api/admin/logout') return next();
    if (!isAdmin(c)) return c.json({ error: 'unauthorized' }, 401);
    c.header('Cache-Control', 'no-store');
    return next();
  });

  app.get('/api/admin/me', c => c.body(null, 204));

  app.get('/api/admin/stats', async c => {
    const range = (RANGES as readonly string[]).includes(c.req.query('range') ?? '') ? c.req.query('range') as Range : '7d';
    const rawPath = c.req.query('path');
    const path = rawPath ? measuredPath(rawPath) : null;
    return c.json(await stats(range, path, now()));
  });

  app.get('/api/admin/live', c => streamSSE(c, async stream => {
    c.header('X-Accel-Buffering', 'no');
    let open = true;
    stream.onAbort(() => { open = false; });
    while (open) {
      await stream.writeSSE({ data: JSON.stringify(live.snapshot(now())) });
      await stream.sleep(LIVE_INTERVAL);
    }
  }));

  app.all('/api/*', c => c.json({ error: 'not found' }, 404));

  // --- référencement -------------------------------------------------------------------------------

  app.get('/robots.txt', c => c.text(sitemaps.robots(), 200, { 'Cache-Control': 'public, max-age=3600' }));
  app.get('/sitemap.xml', c => c.body(sitemaps.index(), 200, { 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': 'public, max-age=3600' }));
  app.get('/sitemaps/:file', c => {
    const body = sitemaps.file(c.req.param('file').replace(/\.xml$/, ''));
    if (!body) return c.text('not found', 404);
    return c.body(body, 200, { 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': 'public, max-age=3600' });
  });

  // Sans nginx devant (essai local du build), le serveur sert aussi les fichiers de dist/.
  if (config.serveStatic) {
    app.use('/*', serveStatic({ root: config.distDir, rewriteRequestPath: p => (p === '/' ? '/__no_index__' : p) }));
  }

  // --- pages : index.html avec les balises de la page demandée -------------------------------------

  app.get('*', c => {
    const url = new URL(c.req.url);
    const page = render(url.pathname, url.search, c.req.header('accept-language') ?? null);
    if (!page) return c.text('Site en cours de déploiement', 503);
    return c.html(page.html, page.status, { 'Cache-Control': 'no-cache' });
  });

  return { app, live, lore };
}
