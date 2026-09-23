import { serve } from '@hono/node-server';
import { config } from './config.ts';
import { openDb } from './db.ts';
import { createApp } from './app.ts';
import { purgeOld } from './analytics/stats.ts';

const db = openDb(config.dbPath);
const { app, lore } = createApp(config, db);

const purge = () => {
  const removed = purgeOld(db, config.retentionDays, Date.now());
  if (removed) console.log(`[allodex] ${removed} pages vues de plus de ${config.retentionDays} jours supprimées`);
};
purge();
const timer = setInterval(purge, 6 * 3_600_000);

const server = serve({ fetch: app.fetch, port: config.port, hostname: config.host }, info => {
  console.log(`[allodex] serveur sur http://${info.address}:${info.port} — ${lore.size} entrées du Lorebook indexées`
    + (config.adminPassword ? '' : ' — ADMIN_PASSWORD absent : /stats désactivé'));
});

function stop() {
  clearInterval(timer);
  server.close(() => {
    db.close();
    process.exit(0);
  });
  // Les flux du direct gardent des connexions ouvertes : ne pas attendre indéfiniment.
  setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
