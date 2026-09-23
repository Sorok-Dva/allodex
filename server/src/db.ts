import path from 'node:path';
import mysql from 'mysql2/promise';
import { drizzle, type MySql2Database } from 'drizzle-orm/mysql2';
import { migrate } from 'drizzle-orm/mysql2/migrator';
import { eq } from 'drizzle-orm';
import * as schema from './schema.ts';

export type DB = MySql2Database<typeof schema>;

const MIGRATIONS = path.resolve(import.meta.dirname, '..', 'drizzle');

/** Pool MySQL (`DATABASE_URL`, ex. `mysql://allodex:…@127.0.0.1:3306/allodex`), migrations appliquées. */
export async function openDb(url: string): Promise<{ db: DB; close: () => Promise<void> }> {
  const pool = mysql.createPool({ uri: url, connectionLimit: 10, timezone: 'Z', charset: 'utf8mb4' });
  const db = drizzle(pool, { schema, mode: 'default' });
  await migrate(db, { migrationsFolder: MIGRATIONS });
  return { db, close: () => pool.end() };
}

export async function kvGet(db: DB, name: string): Promise<string | undefined> {
  const [row] = await db.select({ value: schema.kv.value }).from(schema.kv).where(eq(schema.kv.name, name)).limit(1);
  return row?.value;
}

/** Écrit `value` si la clé est libre ; renvoie la valeur finalement stockée (celle du premier arrivé). */
export async function kvInit(db: DB, name: string, value: string): Promise<string> {
  await db.insert(schema.kv).ignore().values({ name, value });
  return (await kvGet(db, name)) ?? value;
}
