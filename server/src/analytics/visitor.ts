import { createHash, randomBytes } from 'node:crypto';
import { like, ne, and } from 'drizzle-orm';
import { kvInit, type DB } from '../db.ts';
import { kv } from '../schema.ts';
import { dayKey } from './time.ts';

/**
 * Visiteur sans cookie : condensat (sel du jour + IP + agent utilisateur). Le sel change chaque
 * jour et l'ancien est effacé : l'IP n'est jamais stockée et le condensat ne peut plus être
 * rapproché d'une personne ni suivi d'un jour à l'autre.
 */
export function createVisitorHasher(db: DB) {
  let day = '';
  let salt: Promise<string> = Promise.resolve('');

  async function saltOf(today: string) {
    // Premier arrivé gagne : deux requêtes simultanées (ou deux processus) convergent sur le même sel.
    const stored = await kvInit(db, `salt:${today}`, randomBytes(32).toString('hex'));
    await db.delete(kv).where(and(like(kv.name, 'salt:%'), ne(kv.name, `salt:${today}`)));
    return stored;
  }

  return async (ip: string, ua: string, ts: number) => {
    const today = dayKey(ts);
    if (today !== day) {
      day = today;
      salt = saltOf(today);
      salt.catch(() => { day = ''; });
    }
    return createHash('sha256').update(`${await salt}|${ip}|${ua}`).digest('hex').slice(0, 20);
  };
}
