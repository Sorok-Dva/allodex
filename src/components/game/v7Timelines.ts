/** Durées en secondes, indépendantes de la cadence de rendu. */
export const CANNON_FLIGHT = 6;
export const IMPACT_DURATION = 1.4;
// Rafale du 21/09 : apparition du menu vers 6,6 s, incendies 03, 01, 02.
export const INTRO_HITS: Record<number, number> = { 3: 6.8, 1: 11, 2: 19.3 };

export const IMPACT_RING_START = .28;
/** Après le choc concentré : expansion, petite rétraction (18 %), puis fondu. */
export function impactEnvelope(age: number) {
  const forward = Math.max(0, Math.min(1, (age - IMPACT_RING_START) / .77));
  const retreat = Math.max(0, Math.min(1, (age - 1.05) / .35));
  return { shape: forward * (1 - .18 * retreat), returning: age > 1.05,
    opacity: age < IMPACT_RING_START || age >= IMPACT_DURATION ? 0 : (1 - retreat) * Math.min(1, (age - IMPACT_RING_START) / .08) };
}

export function cannonPhase(time: number, delay: number, period: number) {
  if (time < delay) return { age: -1, flight: -1, impact: -1 };
  const age = (time - delay) % period;
  return { age, flight: age < CANNON_FLIGHT ? age / CANNON_FLIGHT : -1,
    impact: age >= CANNON_FLIGHT && age < CANNON_FLIGHT + IMPACT_DURATION ? age - CANNON_FLIGHT : -1 };
}

export function destructionPhase(time: number, hit: number) {
  const age = time - hit;
  const fall = Math.max(0, Math.min(1, (age - .9) / 5));
  return { age, incoming: age >= -.9 && age < 0, burning: age >= 0 && fall < 1,
    fall, opacity: 1 - Math.max(0, (fall - .7) / .3), visible: fall < 1 };
}
