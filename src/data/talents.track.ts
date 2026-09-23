import type { TalentEvent } from '@/analytics/api';

/**
 * Suivi des builds du calculateur (contrat : `src/analytics/api.ts`, `TalentEvent`) :
 * - `view` : la page s'ouvre sur un build venu d'un lien ;
 * - `generate` : l'édition se pose (`IDLE` sans nouveau clic), ou la page se ferme, ou le
 *   lien est copié ; les étapes intermédiaires d'une même séance de clics ne partent pas ;
 * - `share` : le lien est copié.
 * Un build n'est envoyé qu'avec au moins un code (`b` ou `b2`) et jamais deux fois de suite.
 */

export type TrackedBuild = { v: string; c: string; b: string | null; b2: string | null };

export const IDLE = 6000;

const keyOf = (x: TrackedBuild) => `${x.v}|${x.c}|${x.b ?? ''}|${x.b2 ?? ''}`;
const hasCode = (x: TrackedBuild) => Boolean(x.b || x.b2);

type Timers = { set: (fn: () => void, ms: number) => number; clear: (id: number) => void };
const browserTimers: Timers = { set: (fn, ms) => window.setTimeout(fn, ms), clear: id => window.clearTimeout(id) };

export function createBuildTracker(send: (event: TalentEvent) => void, lang: () => string, timers: Timers = browserTimers) {
  let known: string | null = null;
  let generated: string | null = null;
  let pending: TrackedBuild | null = null;
  let timer: number | null = null;

  const emit = (kind: TalentEvent['kind'], x: TrackedBuild) => send({ kind, v: x.v, c: x.c, b: x.b, b2: x.b2, lang: lang() });

  function flush() {
    if (timer !== null) { timers.clear(timer); timer = null; }
    if (!pending) return;
    const x = pending;
    pending = null;
    if (keyOf(x) === generated) return;
    generated = keyOf(x);
    emit('generate', x);
  }

  return {
    /** Premier build affiché ; `fromLink` : l'URL d'arrivée en portait un, valide. */
    landed(x: TrackedBuild, fromLink: boolean) {
      known = keyOf(x);
      if (fromLink && hasCode(x)) emit('view', x);
    },
    /** Le build affiché a changé (clic, remise à zéro, autre classe…). */
    changed(x: TrackedBuild) {
      const key = keyOf(x);
      if (key === known) return;
      known = key;
      if (timer !== null) { timers.clear(timer); timer = null; }
      pending = hasCode(x) ? x : null;
      if (pending) timer = timers.set(flush, IDLE);
    },
    shared(x: TrackedBuild) {
      if (!hasCode(x)) return;
      flush();
      emit('share', x);
    },
    flush,
  };
}
