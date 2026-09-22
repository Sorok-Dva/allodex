/**
 * Cinématiques du jeu (`public/game/cinematics/cinematics.json`, écrit par
 * `tools/extract_cinematics.py`) et logique du « film » d'une faction : ses cinématiques
 * et les communes, dans l'ordre chronologique du manifeste, enchaînées bout à bout.
 */
import type { Lang } from '@/lib/i18n/messages';

const BASE = '/game/cinematics';

export type Faction = 'league' | 'empire';
export type CinematicFaction = Faction | 'common';
export type LocalizedText = { fr: string; en: string };
export type SubtitleLang = 'fr' | 'en' | 'ru';

export type CinematicTrack = { lang: SubtitleLang; label: string; src: string; lines: number };

export type Cinematic = {
  id: string;
  title: LocalizedText;
  faction: CinematicFaction;
  /** Clé de chronologie : le film trie ses cinématiques par `order` croissant. */
  order: number;
  arc: string;
  version: string;
  /** Durée en secondes. */
  duration: number;
  /** `null` = vidéo non extraite (client absent au moment de l'extraction). */
  files: { webm: string; mp4: string; poster: string } | null;
  tracks: CinematicTrack[];
  /** Langue des voix incrustées ; `null` = musique et effets seulement. */
  audio: { language: SubtitleLang | null };
  subtitles: {
    status: 'official' | 'none';
    lines: number;
    /** `client` : durée du jeu depuis 0 ; `measured` : départs mesurés sur la voix. */
    timing: 'client' | 'measured' | 'sequential' | null;
  };
  source: { client: string; pak: string; entry: string; event: string };
  chronology: string;
  note?: string;
};

export type CinematicArc = { title: LocalizedText; version: string };
export type CinematicsIndex = { arcs: Record<string, CinematicArc>; cinematics: Cinematic[] };

/** Un chapitre du film : la cinématique et sa place (secondes) dans la durée totale. */
export type Chapter = { cinematic: Cinematic; start: number; end: number };

export const FACTIONS: readonly Faction[] = ['league', 'empire'];

export const cinematicFile = (file: string) => `${BASE}/${file}`;

export async function loadCinematics(fetcher: typeof fetch = fetch): Promise<CinematicsIndex | null> {
  try {
    const res = await fetcher(`${BASE}/cinematics.json`);
    if (!res.ok) return null;
    const data = (await res.json()) as CinematicsIndex;
    return data && Array.isArray(data.cinematics) ? data : null;
  } catch {
    return null;
  }
}

export const isFaction = (value: string | null | undefined): value is Faction =>
  value === 'league' || value === 'empire';

/** Film d'une faction : ses cinématiques et les communes extraites, dans l'ordre chronologique. */
export function filmFor(cinematics: readonly Cinematic[], faction: Faction): Cinematic[] {
  return cinematics
    .filter(c => (c.faction === faction || c.faction === 'common') && c.files !== null)
    .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
}

/** Chapitres du film, avec leurs bornes dans la durée totale. */
export function chaptersOf(film: readonly Cinematic[]): Chapter[] {
  let t = 0;
  return film.map(cinematic => {
    const chapter = { cinematic, start: t, end: t + cinematic.duration };
    t = chapter.end;
    return chapter;
  });
}

export const filmDuration = (film: readonly Cinematic[]) => film.reduce((sum, c) => sum + c.duration, 0);

/** Chapitre suivant, `null` à la fin du film. */
export const nextIndex = (film: readonly unknown[], index: number): number | null =>
  index + 1 < film.length ? index + 1 : null;

/** Chapitre qui contient l'instant `t` (secondes) du film. */
export function chapterAt(chapters: readonly Chapter[], t: number): number {
  const i = chapters.findIndex(ch => t < ch.end);
  return i === -1 ? Math.max(0, chapters.length - 1) : i;
}

/** Position dans le film d'un instant `time` de la cinématique `index`. */
export const filmTime = (chapters: readonly Chapter[], index: number, time: number) =>
  (chapters[index]?.start ?? 0) + time;

/**
 * Langues de sous-titres proposées par le film (réunion des pistes de ses chapitres),
 * dans l'ordre fr, en, ru.
 */
export function subtitleLangs(film: readonly Cinematic[]): SubtitleLang[] {
  const present = new Set(film.flatMap(c => c.tracks.map(t => t.lang)));
  return (['fr', 'en', 'ru'] as const).filter(lang => present.has(lang));
}

/** Langue de sous-titres par défaut : celle de l'interface si le film l'a, sinon la première. */
export function defaultSubtitleLang(film: readonly Cinematic[], lang: Lang): SubtitleLang | null {
  const langs = subtitleLangs(film);
  return langs.includes(lang) ? lang : langs[0] ?? null;
}

/** Piste d'une cinématique dans la langue voulue (aucune si elle n'existe pas). */
export const trackFor = (cinematic: Cinematic, lang: SubtitleLang | null) =>
  lang ? cinematic.tracks.find(t => t.lang === lang) ?? null : null;

/** Chapitres regroupés par arc consécutif (titres de section de la liste des chapitres). */
export function groupByArc(chapters: readonly Chapter[]): { arc: string; items: { chapter: Chapter; index: number }[] }[] {
  const groups: { arc: string; items: { chapter: Chapter; index: number }[] }[] = [];
  chapters.forEach((chapter, index) => {
    const last = groups[groups.length - 1];
    if (last && last.arc === chapter.cinematic.arc) last.items.push({ chapter, index });
    else groups.push({ arc: chapter.cinematic.arc, items: [{ chapter, index }] });
  });
  return groups;
}

/** « 1:05 » / « 1:02:05 ». */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
