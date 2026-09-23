import fs from 'node:fs';
import path from 'node:path';
import { LORE_SECTIONS, excerpt, type LoreEntry, type LoreLang, type LoreSection } from '../../../src/seo/meta.ts';

/**
 * Index du Lorebook pour les métadonnées et le plan du site, lu dans `dist/game/lorebook/`
 * (formats de `tools/build_lorebook.py`, voir `src/screens/LorebookScreen/lorebook.logic.ts`).
 * Les listes sont chargées au démarrage ; les textes, par bloc et à la demande.
 */

type TextRec = [key: string, text: string | 0, flags: number, extra?: unknown];
type Body = { t?: TextRec[]; s?: string; f?: [string, string][]; i?: { t?: TextRec[] }[]; n?: string };
type ListRow = [id: string, group: number, chunk: number, flags: number, title: string, subtitle: string];

const FALLBACK: Record<LoreLang, LoreLang[]> = { en: ['en', 'fr', 'ru'], fr: ['fr', 'en', 'ru'], ru: ['ru', 'en', 'fr'] };
const CHUNK_CACHE = 48;

/** Texte brut d'un paragraphe Markdown léger (titres, gras, italique, puces, liens). */
export function plain(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*?([^*]+)\*\*?/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Extrait d'une entrée : premier texte présent, sinon celui du premier élément, sinon sous-titre et caractéristiques. */
export function describe(body: Body | undefined): string {
  if (!body) return '';
  const first = (recs?: TextRec[]) => recs?.find(r => typeof r[1] === 'string' && r[1].trim())?.[1] as string | undefined;
  const text = first(body.t) ?? body.i?.map(item => first(item.t)).find(Boolean);
  if (text) return excerpt(plain(text));
  const facts = (body.f ?? []).map(([, value]) => value).filter(Boolean);
  return excerpt([...new Set([body.s, ...facts].filter(Boolean))].join(' · '));
}

/** Bloc d'une entrée d'une section cachée : même dichotomie que le client (`chunkForId`). */
function chunkForId(id: string, firsts: readonly number[]): number {
  const rid = /^r(\d+)$/.exec(id);
  if (!rid || !firsts.length) return -1;
  const n = Number(rid[1]);
  let lo = 0, hi = firsts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (firsts[mid] <= n) lo = mid; else hi = mid - 1;
  }
  return firsts[lo] <= n ? lo : -1;
}

function readJson<T>(file: string): T | undefined {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) as T; } catch { return undefined; }
}

export function createLoreIndex(dir: string) {
  const rows = new Map<string, { chunk: number; titles: Partial<Record<LoreLang, string>> }>();
  const ids = Object.fromEntries(LORE_SECTIONS.map(s => [s, [] as string[]])) as Record<(typeof LORE_SECTIONS)[number], string[]>;
  for (const section of LORE_SECTIONS) {
    for (const lang of ['en', 'fr', 'ru'] as const) {
      const list = readJson<{ rows: ListRow[] }>(path.join(dir, 'list', lang, `${section}.json`));
      for (const [id, , chunk, , title] of list?.rows ?? []) {
        const key = `${section}/${id}`;
        let row = rows.get(key);
        if (!row) {
          rows.set(key, row = { chunk, titles: {} });
          ids[section].push(id);
        }
        row.titles[lang] = title;
      }
    }
  }
  const dialogueFirsts = readJson<{ first: number[] }>(path.join(dir, 'list', 'dialogues-index.json'))?.first ?? [];

  const chunks = new Map<string, Record<string, Body> | undefined>();
  function body(section: LoreSection, lang: LoreLang, chunk: number, id: string): Body | undefined {
    const key = `${lang}/${section}-${chunk}`;
    let data = chunks.get(key);
    if (data === undefined && !chunks.has(key)) {
      data = readJson<Record<string, Body>>(path.join(dir, 'text', lang, `${section}-${chunk}.json`));
      chunks.set(key, data);
      if (chunks.size > CHUNK_CACHE) chunks.delete(chunks.keys().next().value!);
    } else {
      // Remis en fin de file : le cache garde les blocs récemment demandés.
      chunks.delete(key);
      chunks.set(key, data);
    }
    return data?.[id];
  }

  function resolve(section: string, id: string, lang: LoreLang): LoreEntry | undefined {
    if (section === 'dialogues') {
      const chunk = chunkForId(id, dialogueFirsts);
      if (chunk < 0) return undefined;
      const bodies = FALLBACK[lang].map(l => body('dialogues', l, chunk, id));
      const own = bodies.find(Boolean);
      if (!own) return undefined;
      return { section: 'dialogues', id, title: own.n ?? id, description: bodies.map(describe).find(Boolean) ?? '' };
    }
    const row = rows.get(`${section}/${id}`);
    if (!row) return undefined;
    const title = FALLBACK[lang].map(l => row.titles[l]).find(Boolean) ?? id;
    let description = '';
    for (const l of FALLBACK[lang]) {
      description = describe(body(section as LoreSection, l, row.chunk, id));
      if (description) break;
    }
    return { section: section as LoreSection, id, title, description };
  }

  return { resolve, ids, size: rows.size };
}

export type LoreIndex = ReturnType<typeof createLoreIndex>;
