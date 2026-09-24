/**
 * Boucle de marche du lecteur d'auras (fonctions pures, testées sans rendu) : trajectoire, clip de
 * déplacement, composants d'état des empreintes, instants de semis.
 *
 * Règles du lecteur (le client ne fait pas marcher l'avatar tout seul) : un cercle de
 * `WALK_RADIUS` m autour de l'origine, parcouru à la vitesse de course du gabarit
 * (`AnimationProperties.walkForward`, 3,5 m/s pour les Kanians), l'avatar tourné dans le sens de
 * la marche. Le client joue `run` à cette vitesse : c'est l'état que les empreintes attendent.
 */

export const WALK_RADIUS = 3;
/** Vitesse de course (m/s) à défaut de celle du gabarit. */
export const WALK_SPEED = 3.5;

/** Clips de marche d'un gabarit (`walk/<gabarit>.glb`) et sa vitesse de course. */
export type AuraWalk = { url: string; clips: Record<string, number>; speed?: number };

/**
 * Pose sur le cercle après `distance` m : position et rotation autour de Z. Le modèle regarde
 * −Y (le lecteur le montre de face, caméra en −Y) : −Y local suit la tangente.
 */
export function walkPose(distance: number, radius = WALK_RADIUS): { x: number; y: number; rz: number } {
  const a = distance / radius;
  const x = radius * Math.cos(a);
  const y = radius * Math.sin(a);
  const dx = -Math.sin(a);
  const dy = Math.cos(a);
  return { x, y, rz: Math.atan2(dx, -dy) };
}

/** Clip de déplacement joué pendant la marche : `run` s'il existe, sinon `walk`. */
export function moveClip(clips: Record<string, number> | undefined): string | null {
  if (!clips) return null;
  if (clips.run) return 'run';
  if (clips.walk) return 'walk';
  return null;
}

/** Un composant d'état (`StateComponent`) est montré quand l'avatar joue l'une de ses animations. */
export function stateShown(states: string[] | null | undefined, clip: string | null): boolean {
  if (!states) return true;
  return !!clip && states.includes(clip);
}

/**
 * Instants de semis d'un `EmitterVisObjComponent` dans `(from, to]` : `rate` par seconde, le
 * premier à `origin + start` (`origin` : moment où son gabarit est apparu, `start` : son
 * `DelayComponent`).
 */
export function seedTimes(from: number, to: number, origin: number, start: number, rate: number): number[] {
  if (!(rate > 0) || to <= from) return [];
  const period = 1 / rate;
  const first = origin + start;
  const k0 = Math.max(0, Math.floor((from - first) / period) + 1);
  const out: number[] = [];
  for (let k = k0; ; k += 1) {
    const t = first + k * period;
    if (t > to) break;
    if (t > from) out.push(t);
    if (out.length > 64) break;
  }
  return out;
}
