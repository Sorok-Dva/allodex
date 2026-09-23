/**
 * Accès au backend d'audience (contrat : `src/analytics/api.ts`). La maquette de
 * développement (`mock.ts`) expose la même interface.
 */
import type { LiveSnapshot, Range, StatsResponse } from '@/analytics/api';
import { statsRequestUrl } from './format';

export class UnauthorizedError extends Error {
  constructor() { super('Session expirée'); }
}

export type LiveStatus = 'connecting' | 'open' | 'reconnecting';

export type LiveHandlers = {
  onSnapshot: (s: LiveSnapshot) => void;
  onStatus: (s: LiveStatus) => void;
  onUnauthorized: () => void;
};

export type StatsSource = {
  /** `true` si la session d'administration est ouverte. */
  me(): Promise<boolean>;
  /** `true` si le mot de passe est accepté. */
  login(password: string): Promise<boolean>;
  logout(): Promise<void>;
  stats(range: Range, path: string | null, signal?: AbortSignal): Promise<StatsResponse>;
  /** Abonnement au direct ; renvoie la fonction de désabonnement. */
  live(handlers: LiveHandlers): () => void;
};

const opts: RequestInit = { credentials: 'same-origin' };

/** Nouvelle tentative après une coupure définitive du flux (réponse non 200). */
const RETRY_MS = 5000;

export const httpSource: StatsSource = {
  async me() {
    const r = await fetch('/api/admin/me', { ...opts, cache: 'no-store' });
    if (r.status === 401) return false;
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return true;
  },

  async login(password) {
    const r = await fetch('/api/admin/login', {
      ...opts, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }),
    });
    if (r.status === 401) return false;
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return true;
  },

  async logout() {
    await fetch('/api/admin/logout', { ...opts, method: 'POST' });
  },

  async stats(range, path, signal) {
    const r = await fetch(statsRequestUrl(range, path), { ...opts, signal, cache: 'no-store' });
    if (r.status === 401) throw new UnauthorizedError();
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()) as StatsResponse;
  },

  live({ onSnapshot, onStatus, onUnauthorized }) {
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const open = () => {
      if (stopped) return;
      onStatus('connecting');
      es = new EventSource('/api/admin/live', { withCredentials: true });
      es.onopen = () => onStatus('open');
      es.onmessage = e => {
        try { onSnapshot(JSON.parse(e.data) as LiveSnapshot); } catch { /* message illisible : ignoré */ }
      };
      es.onerror = () => {
        onStatus('reconnecting');
        // EventSource se reconnecte seul après une coupure réseau (état CONNECTING) ; une
        // réponse non 200 (un 401 notamment) le ferme pour de bon : on vérifie la session.
        if (!es || es.readyState !== EventSource.CLOSED) return;
        es.close();
        httpSource.me()
          .then(ok => { if (stopped) return; if (ok) timer = setTimeout(open, RETRY_MS); else onUnauthorized(); })
          .catch(() => { if (!stopped) timer = setTimeout(open, RETRY_MS); });
      };
    };

    open();
    return () => { stopped = true; clearTimeout(timer); es?.close(); };
  },
};
