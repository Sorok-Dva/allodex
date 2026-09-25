/**
 * Boucle de marche du lecteur d'auras (fonctions pures, testées sans rendu) : trajectoire, clip de
 * déplacement, composants d'état des empreintes, instants de semis.
 *
 * Règles du lecteur (le client ne fait pas marcher l'avatar tout seul) : un cercle de
 * `WALK_RADIUS` m autour de l'origine, parcouru **en marchant** — clip `walk`, à la vitesse de
 * marche du gabarit (`AnimationProperties.walk` : 2,1 m/s pour KaniaMale, 1,7 pour KaniaFemale),
 * celle à laquelle recule le pied posé du clip : pas de glissement. L'avatar est tourné dans le
 * sens de la marche. `run` (à `walkForward`, 3,5 m/s) ne sert qu'à un gabarit sans `walk`.
 */

export const WALK_RADIUS = 3;
/** Vitesse de marche (m/s) à défaut de celle du gabarit (KaniaMale). */
export const WALK_SPEED = 2.1;
/** Vitesse de course (m/s) à défaut de celle du gabarit (`walkForward`, la même partout). */
export const RUN_SPEED = 3.5;

/** Instants (s, dans le cycle du clip) où chaque pied se pose. */
export type FootSteps = { L?: number[]; R?: number[] };

/**
 * Clips de marche d'un gabarit (`walk/<gabarit>.glb`), ses vitesses de marche (`speed`) et de
 * course (`runSpeed`), les pas de chaque clip (`steps`) et son allure propre (`pace`, m/s : vitesse
 * à laquelle recule le pied posé, à l'échelle du modèle).
 */
export type AuraWalk = {
  url: string; clips: Record<string, number>; speed?: number; runSpeed?: number; steps?: Record<string, FootSteps>;
  pace?: Record<string, number>;
};

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

/** Clip de déplacement joué pendant la marche : `walk` s'il existe, sinon `run`. */
export function moveClip(clips: Record<string, number> | undefined): string | null {
  if (!clips) return null;
  if (clips.walk) return 'walk';
  if (clips.run) return 'run';
  return null;
}

/** Vitesse d'avancée (m/s) du clip joué : de marche pour `walk`, de course pour `run`. */
export function moveSpeed(walk: Pick<AuraWalk, 'speed' | 'runSpeed'> | null | undefined, clip: string | null): number {
  if (clip === 'run') return walk?.runSpeed || RUN_SPEED;
  return walk?.speed || WALK_SPEED;
}

/**
 * Cadence du clip joué : vitesse d'avancée ÷ allure propre du clip, pour que le pied posé ne glisse
 * pas (le client étire lui aussi ses animations de déplacement à la vitesse, `moveAnimationsNoScale`
 * faux dans `AnimationProperties`). 1 sans allure connue ; bornée à [0,5 ; 2].
 */
export function clipRate(walk: Pick<AuraWalk, 'speed' | 'runSpeed' | 'pace'> | null | undefined, clip: string | null): number {
  const pace = clip ? walk?.pace?.[clip] : undefined;
  if (!pace || !(pace > 0)) return 1;
  return Math.min(2, Math.max(0.5, moveSpeed(walk, clip) / pace));
}

/**
 * Pied d'une empreinte : le client nomme ses deux gabarits `…L` et `…R` (`PremiumTrace_Step_01L`) ;
 * à défaut, le côté de son point de semis (+X à gauche, le modèle regardant −Y).
 */
export function footOf(vots: string[], point: number[]): 'L' | 'R' | null {
  const tail = vots.map(v => /([LR])$/.exec(v)?.[1]).find(Boolean);
  if (tail === 'L' || tail === 'R') return tail;
  if (point[0] > 0) return 'L';
  if (point[0] < 0) return 'R';
  return null;
}

/**
 * Instants absolus dans `(from, to]` où le clip (cycle de `cycle` s, en boucle depuis t = 0) pose
 * le pied, `contacts` étant les instants de pose dans le cycle : les empreintes suivent les pas.
 */
export function stepTimes(from: number, to: number, cycle: number, contacts: number[]): number[] {
  if (!(cycle > 0) || to <= from || !contacts.length) return [];
  const out: number[] = [];
  for (let k = Math.floor(from / cycle); k * cycle <= to && out.length <= 64; k += 1) {
    for (const c of contacts) {
      const t = k * cycle + c;
      if (t > from && t <= to) out.push(t);
    }
  }
  return out.sort((a, b) => a - b);
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
