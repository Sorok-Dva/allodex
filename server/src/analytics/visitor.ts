import { createHash, randomBytes } from 'node:crypto';
import { kvGet, kvSet, type DB } from '../db.ts';
import { dayKey } from './time.ts';

/**
 * Visiteur sans cookie : condensat (sel du jour + IP + agent utilisateur). Le sel change chaque
 * jour et l'ancien est effacé : l'IP n'est jamais stockée et le condensat ne peut plus être
 * rapproché d'une personne ni suivi d'un jour à l'autre.
 */
export function createVisitorHasher(db: DB) {
  let day = '';
  let salt = '';
  return (ip: string, ua: string, ts: number) => {
    const today = dayKey(ts);
    if (today !== day) {
      day = today;
      salt = kvGet(db, `salt:${today}`) ?? '';
      if (!salt) {
        salt = randomBytes(32).toString('hex');
        db.transaction(() => {
          db.prepare("DELETE FROM kv WHERE key LIKE 'salt:%'").run();
          kvSet(db, `salt:${today}`, salt);
        })();
      }
    }
    return createHash('sha256').update(`${salt}|${ip}|${ua}`).digest('hex').slice(0, 20);
  };
}
