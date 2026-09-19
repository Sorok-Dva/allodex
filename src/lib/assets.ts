const BASE = '/game';
type Size = { w: number; h: number };
type SpriteSlice = [top: number, right: number, bottom: number, left: number];
type SpriteInfo = { w: number; h: number; slice: SpriteSlice | null };
export type AudioMeta = { duration: number; loop: boolean };

let manifest: Record<string, Size> | null = null;
let sprites: Record<string, SpriteInfo> | null = null;
let audioIndex: Record<string, AudioMeta> | null = null;

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
  const [texturesJson, spritesJson, audioJson] = await Promise.all([
    fetchJson<{ textures?: Record<string, Size> }>(`${BASE}/manifest.json`),
    fetchJson<Record<string, SpriteInfo>>(`${BASE}/sprites.json`),
    fetchJson<Record<string, AudioMeta>>(`${BASE}/audio.json`),
  ]);
  manifest = texturesJson?.textures ?? {};
  sprites = spritesJson ?? {};
  audioIndex = audioJson ?? {};
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

/** Racines de textures du client effectivement utilisées par le site. */
export const T = {
  medals: 'Interface/Ingame/Medals/Textures',
  main2: 'Interface/Wrap/MainMenu/Main2',
  pinMenu: 'Interface/Ingame/ContextPinMenu3/textures',
} as const;
