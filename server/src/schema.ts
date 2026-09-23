import { bigint, boolean, char, index, int, mysqlTable, text, varchar } from 'drizzle-orm/mysql-core';

/**
 * Schéma de la base (MySQL 5.7+ / MariaDB 10.3+). Après une modification : `npm run db:generate`
 * écrit la migration dans `drizzle/`, appliquée au démarrage du serveur. Ne jamais modifier une
 * migration publiée.
 */

/** Réglages internes : sel du jour des visiteurs, secret des sessions d'administration. */
export const kv = mysqlTable('kv', {
  name: varchar('name', { length: 64 }).primaryKey(),
  value: text('value').notNull(),
});

export const pageviews = mysqlTable('pageviews', {
  /** Identifiant de la vue, choisi par le traceur. */
  id: varchar('id', { length: 40 }).primaryKey(),
  /** Millisecondes depuis l'époque. */
  ts: bigint('ts', { mode: 'number' }).notNull(),
  /** AAAA-MM-JJ, heure de Paris. */
  day: char('day', { length: 10 }).notNull(),
  /** Début de l'heure, en millisecondes. */
  hour: bigint('hour', { mode: 'number' }).notNull(),
  session: varchar('session', { length: 40 }).notNull(),
  /** Condensat du jour, voir analytics/visitor.ts. */
  visitor: char('visitor', { length: 20 }).notNull(),
  path: varchar('path', { length: 512 }).notNull(),
  section: varchar('section', { length: 128 }).notNull(),
  entry: boolean('entry').notNull().default(false),
  referrer: varchar('referrer', { length: 100 }),
  lang: varchar('lang', { length: 8 }),
  device: varchar('device', { length: 16 }),
  browser: varchar('browser', { length: 32 }),
  os: varchar('os', { length: 32 }),
  /** Millisecondes de visibilité, mises à jour par les pings et la fin de vue. */
  duration: int('duration'),
}, t => [
  index('pageviews_ts').on(t.ts),
  index('pageviews_path_ts').on(t.path, t.ts),
  index('pageviews_session').on(t.session),
]);
