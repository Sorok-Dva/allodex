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
/** Teinte de la créature (`CreatureColorAction`) : ARGB atteint en `timeOn` s ; mode du client. */
export type TintEvent = { t: number; color: number; blend: string; priority: number; timeOn: number };
/**
 * Secousse de caméra (`ShakeAction`) : décalages de la caméra image par image (`curve`, x y z,
 * `cameraTranslate` des `AnimatedParameters`), multipliés par `amplitude` ; pleine jusqu'à
 * `radius[0]` m de la victime, nulle au-delà de `radius[1]`.
 */
export type ShakeEvent = { t: number; amplitude?: number; radius?: [number, number]; timeScale?: number; curve?: number[] };
export type FatalityTimeline = {
  end: number;
  victim: VictimStep[];
  scale: ScaleEvent[];
  alpha: AlphaEvent[];
  spawns: SpawnEvent[];
  attached: AttachEvent[];
  caster?: CasterTimeline;
  tints?: TintEvent[];
  shakes?: ShakeEvent[];
  ignored?: string[];
};

/** Résultat de `victimTintAt` : multiplicateur et ajout de couleur (0 à 1 par canal). */
export type Tint = { mul: [number, number, number]; add: [number, number, number] };

/**
 * Teinte de la victime à `t` : parmi les `CreatureColorAction` déjà jouées, la plus prioritaire
 * (à égalité, la dernière) ; sa couleur est atteinte en `timeOn` s depuis le blanc, pondérée par
 * son alpha. `DEFAULT`/`MUL`/`DARKEN`/`NORMAL` multiplient, `ADD`/`SCREEN` ajoutent,
 * `OVERLAY` multiplie par deux fois la couleur (clair éclaircit, sombre assombrit) —
 * approximations des modes du client, dont le rendu exact n'est pas publié.
 */
export function victimTintAt(timeline: FatalityTimeline, t: number): Tint {
  const out: Tint = { mul: [1, 1, 1], add: [0, 0, 0] };
  let chosen: TintEvent | null = null;
  for (const event of timeline.tints ?? []) {
    if (event.t > t) continue;
    if (!chosen || event.priority >= chosen.priority) chosen = event;
  }
  if (!chosen) return out;
  const v = chosen.color >>> 0;
  const alpha = ((v >>> 24) & 255) / 255;
  const rgb = [((v >>> 16) & 255) / 255, ((v >>> 8) & 255) / 255, (v & 255) / 255];
  const k = alpha * (chosen.timeOn > 0 ? Math.min(1, (t - chosen.t) / chosen.timeOn) : 1);
  for (let i = 0; i < 3; i += 1) {
    if (chosen.blend === 'ADD' || chosen.blend === 'SCREEN') out.add[i] = rgb[i] * k;
    else if (chosen.blend === 'OVERLAY') out.mul[i] = 1 + (2 * rgb[i] - 1) * k;
    else out.mul[i] = 1 + (rgb[i] - 1) * k;
  }
  return out;
}

/** Cadence des courbes de secousse (`AnimatedParameters.fps` vaut 0 dans le client : 30 par défaut). */
export const SHAKE_FPS = 30;

/** Décalage de la caméra (repère du jeu) dû aux secousses actives à `t`, à `distance` m de la victime. */
export function shakeOffsetAt(timeline: FatalityTimeline, t: number, distance: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0];
  for (const shake of timeline.shakes ?? []) {
    const curve = shake.curve ?? [];
    const frames = Math.floor(curve.length / 3);
    const f = (t - shake.t) * SHAKE_FPS;
    if (f < 0 || f >= frames - 1 || frames < 2) continue;
    const [near, far] = shake.radius ?? [Infinity, Infinity];
    const fall = distance <= near ? 1 : distance >= far ? 0 : 1 - (distance - near) / Math.max(far - near, 1e-3);
    const i = Math.floor(f);
    const w = f - i;
    const a = (shake.amplitude ?? 1) * fall;
    for (let c = 0; c < 3; c += 1) out[c] += (curve[3 * i + c] * (1 - w) + curve[3 * i + 3 + c] * w) * a;
  }
  return out;
}
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
