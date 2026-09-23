import type { LiveSnapshot } from '../../../src/analytics/api.ts';

/** Délai sans nouvelle d'un onglet (le traceur envoie un ping toutes les 20 s) avant de le retirer du direct. */
export const LIVE_TTL = 50_000;

type Presence = { visitor: string; path: string; view: string; seen: number };

/** Présence en direct, en mémoire : un onglet ouvert = une session. */
export class Live {
  private sessions = new Map<string, Presence>();

  touch(session: string, presence: Presence) {
    this.sessions.set(session, presence);
  }

  /** Ne retire l'onglet que si `view` est toujours sa vue en cours (un `leave` peut arriver après le `view` suivant). */
  leave(session: string, view: string) {
    if (this.sessions.get(session)?.view === view) this.sessions.delete(session);
  }

  snapshot(now: number): LiveSnapshot {
    const byPath = new Map<string, Set<string>>();
    const all = new Set<string>();
    for (const [session, p] of this.sessions) {
      if (now - p.seen > LIVE_TTL) { this.sessions.delete(session); continue; }
      all.add(p.visitor);
      let set = byPath.get(p.path);
      if (!set) byPath.set(p.path, set = new Set());
      set.add(p.visitor);
    }
    const pages = [...byPath].map(([path, v]) => ({ path, visitors: v.size }))
      .sort((a, b) => b.visitors - a.visitors || a.path.localeCompare(b.path));
    return { t: now, total: all.size, pages };
  }
}
