/**
 * Accès au plan du film depuis la page : route `/__film-plan` du greffon Vite de développement
 * (`tools/vite/filmPlanPlugin.ts`). Injectable pour les tests.
 */
import type { FilmPlan } from './filmPlan';

export const PLAN_ROUTE = '/__film-plan';
export const PLAN_EVENT = 'film-plan:changed';

export type Loaded = { plan: FilmPlan; revision: string; errors: string[] };
export type SaveResult =
  | { ok: true; revision: string }
  | { ok: false; conflict: true; revision: string }
  | { ok: false; conflict: false; error: string };

export type PlanApi = {
  load: () => Promise<Loaded>;
  save: (plan: FilmPlan, baseRevision: string) => Promise<SaveResult>;
  /** Abonnement aux changements du fichier sur disque ; renvoie la désinscription. */
  subscribe: (onChange: (revision: string) => void) => () => void;
};

export const httpPlanApi: PlanApi = {
  async load() {
    const res = await fetch(PLAN_ROUTE, { cache: 'no-store' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
    return { plan: body.plan, revision: body.revision, errors: body.errors ?? [] };
  },
  async save(plan, baseRevision) {
    const res = await fetch(PLAN_ROUTE, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ baseRevision, plan }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return { ok: true, revision: body.revision };
    if (res.status === 409) return { ok: false, conflict: true, revision: body.revision };
    return { ok: false, conflict: false, error: [body.error, ...(body.errors ?? []).slice(0, 5)].filter(Boolean).join(' ; ') || `HTTP ${res.status}` };
  },
  subscribe(onChange) {
    const hot = import.meta.hot;
    if (!hot) return () => {};
    const handler = (data: { revision?: string }) => { if (data?.revision) onChange(data.revision); };
    hot.on(PLAN_EVENT, handler);
    return () => hot.off?.(PLAN_EVENT, handler);
  },
};
