import { bigint, boolean, char, index, int, mysqlTable, text, uniqueIndex, varchar } from 'drizzle-orm/mysql-core';

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

/**
 * Builds du calculateur de talents, un par contenu : l'identifiant est un condensat de la
 * version, de la classe et des deux codes (`b`, `b2`), si bien que le même build, qu'il soit
 * composé, partagé ou ouvert, retombe sur la même ligne. Les compteurs cumulent les
 * événements de `talent_build_events` (une fois par visiteur, par jour et par sorte).
 */
export const talentBuilds = mysqlTable('talent_builds', {
  /** Condensat du contenu (base64url), voir talents/builds.ts. */
  id: char('id', { length: 12 }).primaryKey(),
  version: varchar('version', { length: 16 }).notNull(),
  /** Classe : slug de l'URL (`c`). */
  cls: varchar('class', { length: 32 }).notNull(),
  /** Build I et build II, codés comme dans l'URL (`b`, `b2`) ; null = état de départ. */
  b: varchar('b', { length: 255 }),
  b2: varchar('b2', { length: 255 }),
  /** Joueur auteur du build (« build de X ») : à relier à la future table des joueurs. */
  playerId: int('player_id'),
  generations: int('generations').notNull().default(0),
  shares: int('shares').notNull().default(0),
  views: int('views').notNull().default(0),
  /** Premier et dernier événement, en millisecondes. */
  firstTs: bigint('first_ts', { mode: 'number' }).notNull(),
  lastTs: bigint('last_ts', { mode: 'number' }).notNull(),
}, t => [
  index('talent_builds_class').on(t.version, t.cls),
  index('talent_builds_player').on(t.playerId),
  index('talent_builds_first').on(t.firstTs),
]);

/**
 * Événements des builds : `generate` (build composé dans le calculateur), `share` (lien
 * copié), `view` (build ouvert depuis un lien). Unique par build, sorte, jour et visiteur :
 * un visiteur ne compte qu'une fois par jour pour chaque build et chaque sorte.
 */
export const talentBuildEvents = mysqlTable('talent_build_events', {
  id: bigint('id', { mode: 'number' }).autoincrement().primaryKey(),
  build: char('build', { length: 12 }).notNull(),
  kind: varchar('kind', { length: 12 }).notNull(),
  ts: bigint('ts', { mode: 'number' }).notNull(),
  /** AAAA-MM-JJ, heure de Paris. */
  day: char('day', { length: 10 }).notNull(),
  /** Condensat du jour, voir analytics/visitor.ts. */
  visitor: char('visitor', { length: 20 }).notNull(),
  lang: varchar('lang', { length: 8 }),
}, t => [
  uniqueIndex('talent_build_events_once').on(t.build, t.kind, t.day, t.visitor),
  index('talent_build_events_ts').on(t.ts),
]);
