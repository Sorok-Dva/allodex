/**
 * Chronologie d'une cinématique moteur (`public/game/cinematics/engine/<id>/scene.json`, écrit par
 * `tools/extract_engine_cutscene.py`) : trajectoire de caméra, répliques, clips des acteurs.
 * Fonctions pures, testées sans WebGL.
 */
import type { SubtitleLang } from '@/lib/cinematics';

export type Vec3 = [number, number, number];
export type CameraKey = { t: number; p: Vec3 };

export type EngineVoice = { event: string; ogg: string; mp3: string; duration: number };

export type EngineLine = {
  n: number;
  start: number;
  duration: number;
  speaker: string | null;
  voice: EngineVoice | null;
  animations: string[];
  /** Clips joués à la suite par le locuteur (animations de son `ClientData`), puis l'attente. */
  clips?: string[];
  text: Partial<Record<SubtitleLang, string>>;
};

export type PathKey = { t: number; p: Vec3; yaw?: number };

export type EngineActor = {
  id: string;
  glb: string;
  name: { ru: string; en: string };
  /** Trajet (au moins une clé) : position, lacet ; interpolé linéairement, dernière clé tenue. */
  path: PathKey[];
  scale: number;
  idle: string;
  talk: string | null;
  /** Clip joué pendant un déplacement du trajet. */
  move?: string | null;
  animations: Record<string, number>;
  /** Instant d'apparition (s). */
  appear?: number;
  /** Intervalles de présence (PNJ invoqués puis retirés) ; remplace `appear` quand il est donné. */
  presence?: [number, number][];
  /** Lumière à sa position (ambiante + ponctuelles de la carte), unités du jeu (1 = 0x80). */
  light?: Vec3 | null;
};

export type EngineLight = {
  ambient?: number;
  ambientFactor?: number;
  diffuse?: number;
  fog?: number;
  fogStart?: number;
  fogEnd?: number;
  pointLight?: number;
  selfIllum?: number;
  sunYaw?: number;
  sunPitch?: number;
  sunDirection?: Vec3;
  /** Désaturation de l'image (0 à 1) d'un changement de temps (`WeatherCreatureVisAction`). */
  desaturation?: number;
};

/** `tilt` : (roulis X, tangage Y) des objets inclinés, composés `Rz(yaw)·Ry·Rx` (Euler `ZYX`). */
export type DecorInstance = { vot: string; p: Vec3; yaw: number; tilt?: [number, number]; scale?: number; light?: [number, number]; ambient?: Vec3 };
export type FxSpawn = { vot: string; t: number; until: number; p?: Vec3; yaw?: number; scale?: number; attach?: string; locator?: string };
export type PostEffect =
  | { t: number; kind: 'fadeIn' | 'fadeOut'; duration: number }
  /** Voile noir d'un `UserPostEffect` : monte en `fadeIn` s dès `t`, tient, redescend en `fadeOut` s à `until`. */
  | { t: number; kind: 'veil'; until: number; fadeIn: number; fadeOut: number };
export type SoundLoop = string | { file: string; t: number; until: number };

export type EngineScene = {
  id: string;
  duration: number;
  up: Vec3;
  mirror: boolean;
  camera: { points: CameraKey[]; targets: CameraKey[]; duration: number; fov: number };
  lines: EngineLine[];
  actors: EngineActor[];
  decor: { glb: string; light: string; instances: DecorInstance[]; sky: { radius: number } | null };
  fx: { glb: string | null; spawns: FxSpawn[] };
  objects: Record<string, import('@/components/scene/FatalityViewer/timeline').FatalityObject>;
  particleAtlas: import('@/components/scene/FatalityViewer/particles').ParticleAtlasMeta | null;
  light: EngineLight;
  sounds: { music: SoundLoop[]; ambience: SoundLoop[]; volume?: Partial<Record<'music' | 'ambience' | 'sfx' | 'voice', number>> };
  post: PostEffect[];
};

/**
 * Position sur une piste de clés : interpolation linéaire entre la clé courante et la suivante
 * (la durée d'un point du jeu est le temps mis à rejoindre le suivant), dernière clé tenue.
 */
export function sampleKeys(keys: readonly CameraKey[], t: number): Vec3 {
  if (!keys.length) return [0, 0, 0];
  if (t <= keys[0].t) return [...keys[0].p];
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i];
    const b = keys[i + 1];
    if (t < b.t) {
      const span = b.t - a.t;
      const u = span > 0 ? (t - a.t) / span : 1;
      return [a.p[0] + (b.p[0] - a.p[0]) * u, a.p[1] + (b.p[1] - a.p[1]) * u, a.p[2] + (b.p[2] - a.p[2]) * u];
    }
  }
  return [...keys[keys.length - 1].p];
}

/** Fin d'affichage d'une réplique : sa durée du client, coupée au départ de la suivante. */
export function lineEnd(lines: readonly EngineLine[], index: number, total: number): number {
  const line = lines[index];
  let end = line.start + line.duration;
  const next = lines[index + 1];
  if (next) end = Math.min(end, next.start);
  return Math.min(end, total);
}

/** Sous-titre affiché à l'instant `t` dans la langue `lang` (`null` si aucun). */
export function subtitleAt(scene: Pick<EngineScene, 'lines' | 'duration'>, t: number, lang: SubtitleLang | null): string | null {
  if (!lang) return null;
  for (let i = 0; i < scene.lines.length; i++) {
    const line = scene.lines[i];
    if (t >= line.start && t < lineEnd(scene.lines, i, scene.duration)) return line.text[lang] ?? null;
  }
  return null;
}

/** Réplique dont la voix joue à l'instant `t`, avec l'instant dans la voix. */
export function voiceAt(lines: readonly EngineLine[], t: number): { index: number; offset: number } | null {
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.voice) continue;
    if (t >= line.start && t < line.start + line.voice.duration) return { index: i, offset: t - line.start };
  }
  return null;
}

/**
 * Clip d'un acteur à l'instant `t` : pendant une réplique dont le `ClientData` demande des animations,
 * ses clips à la suite (durées de l'acteur), sinon le clip de parole de l'acteur (scènes mises en
 * scène), sinon l'attente ; renvoie aussi le temps dans le clip.
 */
export function actorClipAt(actor: Pick<EngineActor, 'id' | 'idle' | 'talk'> & { animations?: Record<string, number> },
  lines: readonly EngineLine[], t: number): { clip: string; time: number } {
  for (const line of lines) {
    if (line.speaker !== actor.id || t < line.start) continue;
    const clips = (line.clips ?? []).filter(c => !actor.animations || c in actor.animations);
    if (clips.length && actor.animations) {
      let local = t - line.start;
      for (const clip of clips) {
        const length = actor.animations[clip] || 0;
        if (local < length) return { clip, time: local };
        local -= length;
      }
      continue;
    }
    if (actor.talk && line.animations.length) {
      const length = line.voice?.duration ?? line.duration;
      if (t < line.start + length) return { clip: actor.talk, time: t - line.start };
    }
  }
  return { clip: actor.idle, time: t };
}

/** Couleur ARGB du client → composantes 0..1 (multipliées par `gain`, bornées à 1). */
export function argb(value: number | undefined, gain = 1): Vec3 {
  const v = value ?? 0;
  return [Math.min(1, (((v >>> 16) & 255) / 255) * gain), Math.min(1, (((v >>> 8) & 255) / 255) * gain), Math.min(1, ((v & 255) / 255) * gain)];
}

/** Position et lacet d'un acteur à l'instant `t`, et s'il se déplace. */
export function pathAt(path: readonly PathKey[], t: number): { p: Vec3; yaw: number; moving: boolean } {
  const first = path[0];
  if (!first) return { p: [0, 0, 0], yaw: 0, moving: false };
  if (t <= first.t || path.length === 1) return { p: [...first.p], yaw: first.yaw ?? 0, moving: false };
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];
    if (t < b.t) {
      const span = b.t - a.t;
      const u = span > 0 ? (t - a.t) / span : 1;
      const moved = a.p.some((v, k) => Math.abs(v - b.p[k]) > 1e-3);
      const ya = a.yaw ?? 0;
      let yb = b.yaw ?? ya;
      while (yb - ya > Math.PI) yb -= 2 * Math.PI;
      while (yb - ya < -Math.PI) yb += 2 * Math.PI;
      return { p: [a.p[0] + (b.p[0] - a.p[0]) * u, a.p[1] + (b.p[1] - a.p[1]) * u, a.p[2] + (b.p[2] - a.p[2]) * u], yaw: ya + (yb - ya) * u, moving: moved };
    }
  }
  const last = path[path.length - 1];
  return { p: [...last.p], yaw: last.yaw ?? 0, moving: false };
}

/** L'acteur est-il en scène à `t` (`presence`, sinon dès `appear`) ? */
export function presentAt(actor: { appear?: number; presence?: [number, number][] }, t: number): boolean {
  if (actor.presence?.length) return actor.presence.some(([a, b]) => t >= a && t < b);
  return t >= (actor.appear ?? 0);
}

/** Opacité du voile noir des fondus (`PostEffectVisAction` : Black_Long, Black_Instant). */
export function veilAt(post: readonly PostEffect[], t: number): number {
  let veil = 0;
  for (const fx of post) {
    const local = t - fx.t;
    if (fx.kind === 'fadeIn' && local < fx.duration) veil = Math.max(veil, local < 0 ? 1 : 1 - local / fx.duration);
    if (fx.kind === 'fadeOut' && local >= 0) veil = Math.max(veil, fx.duration > 0 ? Math.min(1, local / fx.duration) : 1);
    if (fx.kind === 'veil' && local >= 0) {
      const up = fx.fadeIn > 0 ? Math.min(1, local / fx.fadeIn) : 1;
      const after = t - fx.until;
      const down = after <= 0 ? 1 : fx.fadeOut > 0 ? Math.max(0, 1 - after / fx.fadeOut) : 0;
      veil = Math.max(veil, Math.min(up, down));
    }
  }
  return veil;
}

/** Volume d'une source ponctuelle entendue à `distance` m (linéaire jusqu'à `range`). */
export function falloff(distance: number, range = 60): number {
  return Math.max(0, 1 - distance / range);
}
