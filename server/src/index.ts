import { serve } from '@hono/node-server';
import { config } from './config.ts';
import { openDb } from './db.ts';
import { createApp } from './app.ts';
import { purgeOld } from './analytics/stats.ts';
import { purgeOldTalentEvents } from './talents/builds.ts';

if (!config.databaseUrl) {
  console.error('[allodex] DATABASE_URL manquant (voir server/.env.example)');
  process.exit(1);
}

const { db, close } = await openDb(config.databaseUrl);
const { app, lore } = await createApp(config, db);

const purge = () => purgeOld(db, config.retentionDays, Date.now())
  .then(removed => { if (removed) console.log(`[allodex] ${removed} pages vues de plus de ${config.retentionDays} jours supprimées`); })
  .then(() => purgeOldTalentEvents(db, config.retentionDays, Date.now()))
  .then(removed => { if (removed) console.log(`[allodex] ${removed} événements de builds de plus de ${config.retentionDays} jours supprimés`); })
  .catch(err => console.error('[allodex] purge impossible :', err));
void purge();
const timer = setInterval(purge, 6 * 3_600_000);

const server = serve({ fetch: app.fetch, port: config.port, hostname: config.host }, info => {
  console.log(`[allodex] serveur sur http://${info.address}:${info.port} — ${lore.size} entrées du Lorebook indexées`
    + (config.adminPassword ? '' : ' — ADMIN_PASSWORD absent : /stats désactivé'));
});

function stop() {
  clearInterval(timer);
  server.close(() => { void close().finally(() => process.exit(0)); });
  // Les flux du direct gardent des connexions ouvertes : ne pas attendre indéfiniment.
  setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
