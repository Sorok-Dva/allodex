import path from 'node:path';
import { SITE_URL } from '../../src/seo/meta.ts';

const serverDir = path.resolve(import.meta.dirname, '..');

// `server/.env` facultatif ; les variables déjà présentes dans l'environnement l'emportent.
try { process.loadEnvFile(path.join(serverDir, '.env')); } catch { /* pas de fichier */ }

const env = process.env;

export const config = {
  port: Number(env.PORT ?? 8787),
  host: env.HOST ?? '127.0.0.1',
  siteUrl: (env.SITE_URL ?? SITE_URL).replace(/\/+$/, ''),
  /** `mysql://utilisateur:motdepasse@hôte:3306/base` */
  databaseUrl: env.DATABASE_URL ?? '',
  distDir: path.resolve(serverDir, env.DIST_DIR ?? '../dist'),
  adminPassword: env.ADMIN_PASSWORD ?? '',
  sessionSecret: env.SESSION_SECRET ?? '',
  serveStatic: env.SERVE_STATIC === '1',
  /** Domaines du site : un référent de l'un d'eux n'est pas une provenance. */
  ownHosts: (env.OWN_HOSTS ?? 'allodex.eu,allodex.online,allodex.allods-developers.eu,localhost,127.0.0.1').split(',').map(h => h.trim()),
  /** Durée de conservation des pages vues (13 mois, plafond recommandé par la CNIL). */
  retentionDays: Number(env.RETENTION_DAYS ?? 395),
};

export type Config = typeof config;
