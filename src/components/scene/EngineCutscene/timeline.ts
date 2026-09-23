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
  text: Partial<Record<SubtitleLang, string>>;
};

export type EngineActor = {
  id: string;
  glb: string;
  name: { ru: string; en: string };
  position: Vec3;
  yaw: number;
  scale: number;
  idle: string;
  talk: string | null;
  animations: Record<string, number>;
  /** Instant d'apparition (s) ; absent = présent dès le début. */
  appear?: number;
  /** Lumière précalculée moyenne du décor autour de l'acteur (0..1), `null` si aucune. */
  light?: Vec3 | null;
};

export type EngineLight = {
  ambient?: number;
  ambientFactor?: number;
  diffuse?: number;
  fog?: number;
  fogStart?: number;
  fogEnd?: number;
  selfIllum?: number;
  sunYaw?: number;
  sunPitch?: number;
};

export type EngineScene = {
  id: string;
  duration: number;
  up: Vec3;
  mirror: boolean;
  camera: { points: CameraKey[]; targets: CameraKey[]; duration: number; fov: number };
  decor: string;
  actors: EngineActor[];
  lines: EngineLine[];
  light: EngineLight;
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
 * Clip d'un acteur à l'instant `t` : le clip de parole pendant une réplique dont le `ClientData`
 * demande une animation (`emoteSpeech`), l'attente sinon ; renvoie aussi le temps dans le clip.
 */
export function actorClipAt(actor: Pick<EngineActor, 'id' | 'idle' | 'talk'>, lines: readonly EngineLine[], t: number): { clip: string; time: number } {
  if (actor.talk) {
    for (const line of lines) {
      if (line.speaker !== actor.id || !line.animations.length) continue;
      const length = line.voice?.duration ?? line.duration;
      if (t >= line.start && t < line.start + length) return { clip: actor.talk, time: t - line.start };
    }
  }
  return { clip: actor.idle, time: t };
}

/** Couleur ARGB du client → composantes 0..1 (multipliées par `gain`, bornées à 1). */
export function argb(value: number | undefined, gain = 1): Vec3 {
  const v = value ?? 0;
  return [Math.min(1, (((v >>> 16) & 255) / 255) * gain), Math.min(1, (((v >>> 8) & 255) / 255) * gain), Math.min(1, ((v & 255) / 255) * gain)];
}
