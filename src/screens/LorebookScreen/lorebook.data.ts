import type { Body, ContentLang, DirRow, ListData, SectionId, Shard } from './lorebook.logic';

/** Chargement à la demande de `public/game/lorebook/` (écrit par `tools/build_lorebook.py`), avec cache. */
const BASE = '/game/lorebook';
const cache = new Map<string, Promise<unknown>>();

export type LoreMeta = {
  sections: Record<SectionId, { count: number; chunks: number; hidden?: boolean; groups: { id: string; count: number }[] }>;
  credit: { line: string; short?: string; url?: string; author?: string };
  translated_by: string;
  entries: number;
  dir_block: number;
  token_min: number;
  stopwords: string[];
};

function get<T>(path: string): Promise<T> {
  let p = cache.get(path) as Promise<T> | undefined;
  if (!p) {
    p = fetch(`${BASE}/${path}`).then(r => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json() as Promise<T>;
    });
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return p;
}

/** Variante qui rend `undefined` au lieu d'échouer (fragment d'index absent = aucun mot). */
function maybe<T>(path: string): Promise<T | undefined> {
  return get<T>(path).catch(() => undefined);
}

export const loadMeta = () => get<LoreMeta>('meta.json');
export const loadList = (lang: ContentLang, section: SectionId) => get<ListData>(`list/${lang}/${section}.json`);
export const loadChunk = (lang: ContentLang, section: SectionId, chunk: number) => get<Record<string, Body>>(`text/${lang}/${section}-${chunk}.json`);
export const loadShard = (lang: ContentLang, key: string) => maybe<Shard>(`search/${lang}/${key}.json`);
export const loadDir = (lang: ContentLang, block: number) => get<DirRow[]>(`dir/${lang}/${block}.json`);
export const loadNames = (lang: ContentLang) => get<Record<string, string>>(`names/${lang}.json`);
export const loadHiddenIndex = (section: SectionId) => get<{ first: number[] }>(`list/${section}-index.json`);

/** Images du matériel communautaire (`tools/build_lore_media.py`) : pleine taille ou vignette. */
export const imageUrl = (id: string, thumb = false) => `/game/lorebook-media/${id}${thumb ? '-t' : ''}.webp`;

/** Réservé aux tests. */
export function clearLoreCache() {
  cache.clear();
}
