/**
 * Lecture des chronologies de fatalité écrites par `tools/extract_fatalities.py`.
 *
 * Tout est fonction pure du temps : l'écran peut se déplacer librement dans la fatalité
 * (barre de lecture, vitesse, pause) et chaque image se recalcule de zéro. Les règles
 * viennent des scripts du client (`tools/fatality_script.py`) ; les rares constantes
 * propres au lecteur sont nommées et justifiées ici.
 */

export type VictimStep = {
  t: number;
  end: number;
  anim?: string;
  speed: number;
  mode: 'CLAMP' | 'LOOP' | 'DIE' | string;
  alternatives?: string[];
};
export type ScaleEvent = { t: number; scale: number };
export type AlphaEvent = { t: number; value: number; fadeMult: number; priority: number };
export type SpawnEvent = {
  t: number;
  vot: string;
  lifeTime: number;
  offset?: [number, number, number];
  rotation?: [number, number, number];
  scale: number;
  isRelative?: boolean;
};
export type AttachEvent = {
  t: number;
  vot: string;
  locator?: string;
  scale: number;
  fadeIn: number;
  fadeOut: number;
  offset?: [number, number, number];
  until?: number;
};
/** Extrémité d'un rayon : un locator de la créature (`Global` = sa racine) et un décalage. */
export type ChannelPoint = { locator: string; shift: [number, number, number] };
/**
 * Rayon (`CreatureChannelDirectAction`) tendu du tueur vers la victime : gabarit modelé sur
 * `length` mètres le long de son axe Y, étiré à la distance réelle, fondus d'entrée et de sortie.
 */
export type ChannelEvent = {
  t: number;
  until: number;
  vot: string;
  fadeIn: number;
  fadeOut: number;
  length: number;
  velocity?: number;
  start?: ChannelPoint | null;
  end?: ChannelPoint | null;
};
/** Script du tueur (`casterFxScript`) : ses animations, ses effets accrochés, ses rayons. */
export type CasterTimeline = { anims: VictimStep[]; attached: AttachEvent[]; channels: ChannelEvent[] };
export type FatalityTimeline = {
  end: number;
  victim: VictimStep[];
  scale: ScaleEvent[];
  alpha: AlphaEvent[];
  spawns: SpawnEvent[];
  attached: AttachEvent[];
  caster?: CasterTimeline;
  ignored?: string[];
};
export type FatalityObject = {
  fadeIn: number;
  fadeOut: number;
  scale: number;
  duration: number;
  loop: boolean;
  orientation?: string;
  sound?: string;
  sfx?: string;
  particles?: import('./particles').ParticleSystemMeta;
  /** Composants accrochés ; `start`/`stop` : fenêtre des `DelayComponent`/`StopVisObjectComponents`. */
  components?: { vot: string; locator: string; start?: number; stop?: number }[];
};

/**
 * Durée prêtée à `CreatureSetTransparencyAction` pour atteindre sa transparence cible, divisée
 * par son `fadeMult` (« multiplicateur de vitesse du fondu », dit le schéma). Le client ne
 * publie pas la vitesse de base : une seconde, valeur qui fait disparaître la victime avant
 * `fadeStartTime + fadeDuration` dans les 26 scripts (le délai qui précède la transparence
 * vaut toujours 0,4 à 1,2 s de moins que `fadeStartTime`).
 */
export const TRANSPARENCY_FADE_SECONDS = 1;

/**
 * Pas d'animation de la victime actif à `t` : le dernier commencé qui n'est pas fini ; s'ils
 * sont tous finis, le dernier commencé (sa dernière pose reste tenue). Une animation courte
 * jouée par-dessus une boucle (sort de l'Écureuil) rend ainsi la main à la boucle.
 */
export function victimStepAt(timeline: FatalityTimeline, t: number): VictimStep | null {
  return stepAt(timeline.victim, t);
}

/** Même règle pour une liste de pas quelconque (animations du tueur). */
export function stepAt(steps: VictimStep[], t: number): VictimStep | null {
  let running: VictimStep | null = null;
  let last: VictimStep | null = null;
  for (const step of steps) {
    if (step.t > t || !step.anim) continue;
    last = step;
    if (t < step.end) running = step;
  }
  return running ?? last;
}

/** Temps local du clip de la victime : vitesse du script, dernière pose tenue (`CLAMP`/`DIE`). */
export function victimClipTime(step: VictimStep, t: number, clipDuration: number): number {
  const local = Math.max(0, Math.min(t, step.end) - step.t) * (step.speed || 1);
  if (step.mode === 'LOOP' && clipDuration > 0) return local % clipDuration;
  return Math.min(local, Math.max(0, clipDuration - 1e-4));
}

/** Échelle de la victime : la dernière `CreatureScaleAction` jouée (1 avant la première). */
export function victimScaleAt(timeline: FatalityTimeline, t: number): number {
  let scale = 1;
  for (const event of timeline.scale) if (event.t <= t) scale = event.scale;
  return scale;
}

/**
 * Opacité de la victime : chaque `CreatureSetTransparencyAction` fait glisser l'opacité vers sa
 * cible en `TRANSPARENCY_FADE_SECONDS / fadeMult` ; puis le fondu de fin de la fatalité
 * (`fadeStartTime`, `fadeDuration`) l'emmène à zéro.
 */
export function victimOpacityAt(timeline: FatalityTimeline, t: number, fadeStart: number, fadeDuration: number): number {
  let value = 1;
  let from = 1;
  let last = -Infinity;
  const events = [...timeline.alpha].sort((a, b) => a.t - b.t);
  for (const event of events) {
    if (event.t > t) break;
    // L'opacité atteinte au moment où l'action précédente est relayée.
    from = last === -Infinity ? 1 : value;
    const span = TRANSPARENCY_FADE_SECONDS / Math.max(event.fadeMult || 1, 1e-3);
    const k = Math.min(1, (t - event.t) / span);
    value = from + (event.value - from) * k;
    last = event.t;
  }
  if (fadeStart > 0 && t >= fadeStart) {
    const k = fadeDuration > 0 ? Math.min(1, (t - fadeStart) / fadeDuration) : 1;
    value *= 1 - k;
  }
  return Math.max(0, Math.min(1, value));
}

/** Enveloppe d'opacité d'un objet d'effet : fondu d'entrée, vie, fondu de sortie. */
export function spawnOpacity(local: number, lifeTime: number, fadeIn: number, fadeOut: number): number {
  if (local < 0 || local > lifeTime + fadeOut) return 0;
  const enter = fadeIn > 0 ? Math.min(1, local / fadeIn) : 1;
  const leave = local <= lifeTime ? 1 : fadeOut > 0 ? 1 - (local - lifeTime) / fadeOut : 0;
  return Math.max(0, Math.min(enter, leave));
}

/** Temps d'animation d'un gabarit : en boucle ou tenu sur sa dernière image. */
export function objectClipTime(local: number, duration: number, loop: boolean): number {
  if (duration <= 0) return 0;
  if (loop) return ((local % duration) + duration) % duration;
  return Math.max(0, Math.min(local, duration - 1e-4));
}

/** Durée totale d'une fatalité : le dernier objet éteint, la dernière animation, le fondu final. */
export function timelineDuration(timeline: FatalityTimeline, objects: Record<string, FatalityObject>,
  fadeStart: number, fadeDuration: number): number {
  let end = Math.max(timeline.end || 0, fadeStart + fadeDuration);
  for (const step of timeline.victim) end = Math.max(end, step.end);
  for (const spawn of timeline.spawns) end = Math.max(end, spawn.t + spawn.lifeTime + (objects[spawn.vot]?.fadeOut ?? 0));
  for (const item of timeline.attached) end = Math.max(end, item.t + (item.fadeIn ?? 0));
  return end;
}

/** Sons déclenchés : l'onde du gabarit posé (et de ses composants) à l'instant de sa pose. */
export function timelineSounds(timeline: FatalityTimeline, objects: Record<string, FatalityObject>): { t: number; sfx: string }[] {
  const out: { t: number; sfx: string }[] = [];
  const visit = (name: string, t: number, depth: number) => {
    const object = objects[name];
    if (!object || depth > 8) return;
    if (object.sfx) out.push({ t, sfx: object.sfx });
    for (const component of object.components ?? []) visit(component.vot, t + (component.start ?? 0), depth + 1);
  };
  for (const spawn of timeline.spawns) visit(spawn.vot, spawn.t, 0);
  for (const item of timeline.attached) visit(item.vot, item.t, 0);
  for (const item of timeline.caster?.attached ?? []) visit(item.vot, item.t, 0);
  for (const item of timeline.caster?.channels ?? []) visit(item.vot, item.t, 0);
  return out.sort((a, b) => a.t - b.t);
}
