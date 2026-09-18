const BASE = '/game';
type Size = { w: number; h: number };
let manifest: Record<string, Size> | null = null;

export async function loadManifest(): Promise<void> {
  try {
    const res = await fetch(`${BASE}/manifest.json`);
    if (!res.ok) throw new Error(String(res.status));
    manifest = (await res.json()).textures ?? {};
  } catch {
    manifest = {};
    if (import.meta.env.DEV) console.warn('[assets] manifest.json absent : lancez `npm run extract`');
  }
}

export const hasAssets = () => manifest !== null && Object.keys(manifest).length > 0;
export const tex = (path: string) => `${BASE}/textures/${path}.png`;
export const texSize = (path: string): Size | undefined => manifest?.[path];
export const video = (name: 'intro' | 'mainmenu') => ({ webm: `${BASE}/video/${name}.webm`, mp4: `${BASE}/video/${name}.mp4` });
export const cursor = (name: string) => `${BASE}/cursors/${name}.cur`;

export const T = {
  medals: 'Interface/Ingame/Medals/Textures',
  login: 'Interface/Wrap/MainMenu/LoginAccount',
  main2: 'Interface/Wrap/MainMenu/Main2',
  cross: 'Interface/Common/Buttons/Cross/Close',
  msgbox: 'Interface/Common/Elements/MsgBox/textures',
} as const;
