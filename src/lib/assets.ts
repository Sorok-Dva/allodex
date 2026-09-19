const BASE = '/game';
type Size = { w: number; h: number };
type SpriteSlice = [top: number, right: number, bottom: number, left: number];
type SpriteInfo = { w: number; h: number; slice: SpriteSlice | null };
export type AudioMeta = { duration: number; loop: boolean };

/** Fichiers des deux formats d'un média, relatifs au dossier de la version. */
type MediaPair = { webm: string; mp4: string };
export type ArchiveTheme = {
  name: string;
  subsong?: number;
  duration: number;
  ogg: string;
  mp3: string;
  alternatives?: string[];
};
/**
 * Une version archivée du jeu (`public/game/archive.json`, écrit par
 * `tools/extract_archive.py`). `media: null` = client absent au moment de
 * l'extraction : la page Chroniques affiche « Média non extrait ».
 */
export type ArchiveEntry = {
  version: string;
  /** Nom de l'add-on (« Power of Metal »), absent avant les add-ons (1.1). */
  name?: string;
  label: string;
  media: 'video' | 'image' | null;
  /** Nom du PNG de fond (`media: 'image'`). */
  background?: string;
  /** Mention affichée quand le fond est une illustration de repli et non la vraie scène. */
  background_note?: string;
  /** Nom du PNG du logo de l'add-on ; absent = aucun client archivé ne le conserve. */
  logo?: string;
  /** Durée de la vidéo de menu, en secondes. */
  duration?: number;
  video?: MediaPair;
  intro?: MediaPair;
  theme?: ArchiveTheme;
  note?: string;
  theme_note?: string;
};

let manifest: Record<string, Size> | null = null;
let sprites: Record<string, SpriteInfo> | null = null;
let audioIndex: Record<string, AudioMeta> | null = null;
let archive: ArchiveEntry[] | null = null;

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function loadManifest(): Promise<void> {
  const [texturesJson, spritesJson, audioJson, archiveJson] = await Promise.all([
    fetchJson<{ textures?: Record<string, Size> }>(`${BASE}/manifest.json`),
    fetchJson<Record<string, SpriteInfo>>(`${BASE}/sprites.json`),
    fetchJson<Record<string, AudioMeta>>(`${BASE}/audio.json`),
    fetchJson<ArchiveEntry[]>(`${BASE}/archive.json`),
  ]);
  manifest = texturesJson?.textures ?? {};
  sprites = spritesJson ?? {};
  audioIndex = audioJson ?? {};
  archive = archiveJson ?? [];
  if (import.meta.env.DEV && !texturesJson) console.warn('[assets] manifest.json absent : lancez `npm run extract`');
}

export const hasAssets = () => manifest !== null && Object.keys(manifest).length > 0;
export const tex = (path: string) => `${BASE}/textures/${path}.png`;
export const texSize = (path: string): Size | undefined => manifest?.[path];
export const video = (name: 'intro' | 'mainmenu') => ({ webm: `${BASE}/video/${name}.webm`, mp4: `${BASE}/video/${name}.mp4` });
export const cursor = (name: string) => `${BASE}/cursors/${name}.cur`;
export const sprite = (name: string) => `${BASE}/sprites/${name}.png`;
export const spriteSize = (name: string): SpriteInfo | undefined => sprites?.[name];
/** URLs des deux formats d'une piste audio, ogg d'abord (ordre attendu des `<source>`). */
export const audioSrc = (name: string) => ({ ogg: `${BASE}/audio/${name}.ogg`, mp3: `${BASE}/audio/${name}.mp3` });
export const audioMeta = (name: string): AudioMeta | undefined => audioIndex?.[name];
/** Versions archivées, dans l'ordre de l'index (croissant) ; tableau vide si absent. */
export const archiveEntries = (): ArchiveEntry[] => archive ?? [];
/** URL d'un fichier d'une version archivée (`background.png`, `menu.webm`, `theme.ogg`…). */
export const archiveFile = (version: string, file: string) => `${BASE}/archive/${version}/${file}`;
/** URL d'un fichier commun à toutes les versions (emblème de chargement). */
export const archiveCommon = (file: string) => `${BASE}/archive/_common/${file}`;

/** Racines de textures du client effectivement utilisées par le site. */
export const T = {
  medals: 'Interface/Ingame/Medals/Textures',
  main2: 'Interface/Wrap/MainMenu/Main2',
  pinMenu: 'Interface/Ingame/ContextPinMenu3/textures',
} as const;
