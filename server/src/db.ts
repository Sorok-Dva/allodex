import fs from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';

export type DB = Database.Database;

/**
 * Migrations, dans l'ordre ; `PRAGMA user_version` retient la dernière appliquée. Ne jamais
 * modifier une migration publiée : en ajouter une nouvelle (comptes, avatars…).
 */
const MIGRATIONS = [
  `CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
   CREATE TABLE pageviews (
     id       TEXT PRIMARY KEY,
     ts       INTEGER NOT NULL,          -- ms depuis l'époque
     day      TEXT NOT NULL,             -- AAAA-MM-JJ, heure de Paris
     hour     INTEGER NOT NULL,          -- début de l'heure, ms
     session  TEXT NOT NULL,
     visitor  TEXT NOT NULL,             -- condensat du jour, voir visitor.ts
     path     TEXT NOT NULL,
     section  TEXT NOT NULL,
     entry    INTEGER NOT NULL DEFAULT 0,
     referrer TEXT,
     lang     TEXT,
     device   TEXT,
     browser  TEXT,
     os       TEXT,
     duration INTEGER                    -- ms de visibilité, mis à jour par ping/leave
   );
   CREATE INDEX pageviews_ts ON pageviews(ts);
   CREATE INDEX pageviews_path_ts ON pageviews(path, ts);
   CREATE INDEX pageviews_session ON pageviews(session);`,
];

export function openDb(file: string): DB {
  if (file !== ':memory:') fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new Database(file);
  db.pragma('journal_mode = WAL');
  db.pragma('synchronous = NORMAL');
  db.pragma('foreign_keys = ON');
  migrate(db);
  return db;
}

function migrate(db: DB) {
  const current = db.pragma('user_version', { simple: true }) as number;
  for (let i = current; i < MIGRATIONS.length; i++) {
    db.transaction(() => {
      db.exec(MIGRATIONS[i]);
      db.pragma(`user_version = ${i + 1}`);
    })();
  }
}

export function kvGet(db: DB, key: string): string | undefined {
  return (db.prepare('SELECT value FROM kv WHERE key = ?').get(key) as { value: string } | undefined)?.value;
}

export function kvSet(db: DB, key: string, value: string) {
  db.prepare('INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value').run(key, value);
}
