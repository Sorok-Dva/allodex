import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { kvInit, type DB } from './db.ts';

export const ADMIN_COOKIE = 'allodex_admin';
export const SESSION_TTL = 30 * 24 * 3_600_000;

const sha = (s: string) => createHash('sha256').update(s).digest();

/**
 * Administration à mot de passe unique (`ADMIN_PASSWORD`). Le cookie porte son échéance
 * signée (HMAC) : rien à stocker côté serveur. Changer `SESSION_SECRET` déconnecte tout le monde.
 * À remplacer par de vrais comptes quand la création d'avatar en aura besoin.
 */
export async function createAuth(db: DB, password: string, configuredSecret: string) {
  const secret = configuredSecret || await kvInit(db, 'session_secret', randomBytes(32).toString('hex'));
  // Le mot de passe entre dans la clé : le changer invalide les sessions ouvertes.
  const sign = (payload: string) => createHmac('sha256', `${secret}|${password}`).update(payload).digest('base64url');

  return {
    enabled: password.length > 0,
    checkPassword(input: unknown) {
      return password.length > 0 && typeof input === 'string' && timingSafeEqual(sha(input), sha(password));
    },
    issue(now: number) {
      const exp = String(now + SESSION_TTL);
      return `${exp}.${sign(exp)}`;
    },
    verify(token: string | undefined, now: number) {
      if (!password || !token) return false;
      const [exp, mac] = token.split('.');
      if (!exp || !mac || Number(exp) < now) return false;
      const expected = Buffer.from(sign(exp));
      const given = Buffer.from(mac);
      return expected.length === given.length && timingSafeEqual(expected, given);
    },
  };
}

export type Auth = Awaited<ReturnType<typeof createAuth>>;
