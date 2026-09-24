/**
 * Logique pure de la page Lorebook : routes, repli des langues du contenu, recherche sur l'index
 * fragmenté, liens automatiques vers les noms propres, fenêtre de la liste virtualisée. Les
 * formats de données sont ceux de `tools/build_lorebook.py` (voir sa docstring).
 */

export const CONTENT_LANGS = ['en', 'fr', 'ru'] as const;
export type ContentLang = (typeof CONTENT_LANGS)[number];
export const SECTIONS = ['timeline', 'atlas', 'library', 'characters', 'secrets', 'quests', 'gallery'] as const;
/** Sections sans onglet ni liste (répliques non rattachées à un PNJ) : recherche et liens seulement. */
export const HIDDEN_SECTIONS = ['dialogues'] as const;
export type SectionId = (typeof SECTIONS)[number] | (typeof HIDDEN_SECTIONS)[number];
export const isHidden = (s: SectionId): boolean => (HIDDEN_SECTIONS as readonly string[]).includes(s);

/** Ordre de repli d'un texte absent dans la langue demandée (même règle que l'outil de construction). */
export const FALLBACK: Record<ContentLang, readonly ContentLang[]> = {
  en: ['en', 'fr', 'ru'],
  fr: ['fr', 'en', 'ru'],
  ru: ['ru', 'en', 'fr'],
};

export const FLAG_COMMUNITY = 1;
export const FLAG_EN_MISSING = 2;
export const FLAG_REVISED = 4;
export const TEXT_REVISED = 1;

/** Image du matériel communautaire : `[id, largeur, hauteur]` (fichiers `<id>.webp` et `<id>-t.webp`). */
export type Img = [id: string, w: number, h: number];
export type TextExtra = { heading?: string; md?: boolean; img?: Img[] };
/** `[clé du champ, texte ou 0 (absent dans cette langue), drapeaux, extra ?]`. */
export type TextRec = [key: string, text: string | 0, flags: number, extra?: TextExtra];
export type LinkRef = [ref: string, title: string];
export type Links = Record<string, LinkRef[]>;
export type Item = { t: TextRec[]; h?: TextRec; n?: number; l?: Links; p?: Img[] };
export type Body = {
  t: TextRec[];
  s?: string;
  f?: [string, string][];
  i?: Item[];
  l?: Links;
  /** Galerie de l'entrée. */
  p?: Img[];
  m?: { era?: string; source?: string; credit?: string; translated?: string; name_official?: boolean };
  /** Sections cachées : titre et drapeaux de l'entrée (pas de ligne de liste). */
  n?: string;
  g?: number;
};
export type ListGroup = { id: string; key?: string; label?: string; count: number };
export type ListRow = [id: string, group: number, chunk: number, flags: number, title: string, subtitle: string];
export type ListData = { groups: ListGroup[]; rows: ListRow[] };
export type DirRow = [section: SectionId, id: string, title: string, flags: number];

// --- routes ----------------------------------------------------------------------------------------

export type LoreRoute =
  | { view: 'home' }
  | { view: 'section'; section: SectionId; group?: string }
  | { view: 'entry'; section: SectionId; id: string }
  | { view: 'search'; q: string };

export const LORE_BASE = '/lorebook';

const isSection = (s: string | undefined): s is SectionId => !!s && ([...SECTIONS, ...HIDDEN_SECTIONS] as readonly string[]).includes(s);

/** `/lorebook`, `/lorebook/<section>[?group=]`, `/lorebook/<section>/<id>`, `/lorebook/search?q=`. */
export function parseLoreRoute(path: string, query: URLSearchParams): LoreRoute {
  const parts = path.replace(/\/+$/, '').split('/').filter(Boolean).map(p => decodeURIComponent(p));
  if (parts[0] !== LORE_BASE.slice(1)) return { view: 'home' };
  if (parts[1] === 'search') return { view: 'search', q: query.get('q') ?? '' };
  if (!isSection(parts[1])) return { view: 'home' };
  if (parts[2]) return { view: 'entry', section: parts[1], id: parts[2] };
  const group = query.get('group') ?? undefined;
  return group ? { view: 'section', section: parts[1], group } : { view: 'section', section: parts[1] };
}

export function lorePath(route: LoreRoute): string {
  switch (route.view) {
    case 'home': return LORE_BASE;
    case 'search': return `${LORE_BASE}/search?q=${encodeURIComponent(route.q)}`;
    case 'section': return `${LORE_BASE}/${route.section}${route.group ? `?group=${encodeURIComponent(route.group)}` : ''}`;
    case 'entry': return `${LORE_BASE}/${route.section}/${encodeURIComponent(route.id)}`;
  }
}

/** « section/id » (références des liens et de l'index des noms) → chemin de l'entrée. */
export function refPath(ref: string): string {
  const [section, id] = ref.split('/');
  return isSection(section) && id ? lorePath({ view: 'entry', section, id }) : LORE_BASE;
}

/**
 * Bloc d'une entrée d'une section cachée : les entrées y sont rangées par rid croissant et
 * `firsts` donne le premier rid de chaque bloc (dichotomie). -1 si l'id n'est pas un rid.
 */
export function chunkForId(id: string, firsts: readonly number[]): number {
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

// --- langues du contenu -----------------------------------------------------------------------------

export type ResolvedText = { key: string; text: string; from: ContentLang | null; revised: boolean; extra?: TextExtra };
export type ResolvedItem = { heading?: ResolvedText; texts: ResolvedText[]; step?: number; links?: Links; images: Img[] };
export type ResolvedBody = {
  texts: ResolvedText[];
  items: ResolvedItem[];
  subtitle?: string;
  facts?: [string, string][];
  links?: Links;
  images: Img[];
  meta?: Body['m'];
};

/** Langues de repli dont il faut charger le bloc pour afficher `body` dans `lang`. */
export function neededFallbacks(body: Body | undefined, lang: ContentLang): ContentLang[] {
  if (!body) return [];
  const recs: TextRec[] = [...body.t, ...(body.i ?? []).flatMap(it => [...(it.h ? [it.h] : []), ...it.t])];
  return recs.some(r => r[1] === 0) ? FALLBACK[lang].slice(1) : [];
}

function pickRec(bodies: Partial<Record<ContentLang, Body>>, lang: ContentLang, get: (b: Body) => TextRec | undefined): ResolvedText | undefined {
  const own = bodies[lang] ? get(bodies[lang]!) : undefined;
  if (!own) return undefined;
  for (const candidate of FALLBACK[lang]) {
    const body = bodies[candidate];
    const rec = body ? get(body) : undefined;
    if (rec && rec[1]) {
      return {
        key: own[0], text: rec[1], from: candidate === lang ? null : candidate,
        revised: candidate === lang && Boolean(rec[2] & TEXT_REVISED), extra: own[3],
      };
    }
  }
  return { key: own[0], text: '', from: null, revised: false, extra: own[3] };
}

/**
 * Corps d'une entrée dans `lang`, chaque texte absent lu dans la première langue de repli qui
 * l'a (`from` = cette langue : badge « pas encore traduit »). Les blocs des trois langues ont les
 * mêmes entrées, champs et éléments dans le même ordre.
 */
export function resolveBody(bodies: Partial<Record<ContentLang, Body>>, lang: ContentLang): ResolvedBody | undefined {
  const base = bodies[lang];
  if (!base) return undefined;
  const texts = base.t.map((_, i) => pickRec(bodies, lang, b => b.t[i])).filter((x): x is ResolvedText => !!x && !!x.text);
  const items = (base.i ?? []).map((it, j) => ({
    heading: it.h ? pickRec(bodies, lang, b => b.i?.[j]?.h) : undefined,
    texts: it.t.map((_, i) => pickRec(bodies, lang, b => b.i?.[j]?.t[i])).filter((x): x is ResolvedText => !!x && !!x.text),
    step: it.n,
    links: it.l,
    images: it.p ?? [],
  }));
  return { texts, items, subtitle: base.s, facts: base.f, links: base.l, images: base.p ?? [], meta: base.m };
}

// --- recherche ---------------------------------------------------------------------------------------

/** Forme de recherche (même règle que `norm_text` de l'outil) : minuscules, sans diacritiques latins, ё → е. */
export function normalize(s: string): string {
  return s.toLowerCase().replace(/ё/g, 'е').normalize('NFD').replace(/[̀-ͯ]/g, '');
}

export function queryTokens(q: string, stopwords: ReadonlySet<string>, min = 3): string[] {
  const out: string[] = [];
  for (const t of normalize(q).match(/[0-9a-zа-я]+/g) ?? []) {
    if (t.length >= min && !stopwords.has(t) && !out.includes(t)) out.push(t);
  }
  return out;
}

/** Nom du fragment d'index : points de code des deux premiers caractères, en hexadécimal. */
export function shardKey(token: string): string {
  return [...token.slice(0, 2)].map(c => c.codePointAt(0)!.toString(16)).join('');
}

export function decodeIds(encoded: string): number[] {
  const out: number[] = [];
  let prev = 0;
  if (!encoded) return out;
  for (const part of encoded.split(',')) {
    prev += parseInt(part, 36);
    out.push(prev);
  }
  return out;
}

/** `"ids|ids titre"` → ids globaux de toutes les entrées et de celles dont le titre contient le mot. */
export function decodePostings(value: string): { all: number[]; title: number[] } {
  const [all, title = ''] = value.split('|');
  return { all: decodeIds(all), title: decodeIds(title) };
}

export type Shard = Record<string, string>;
export type SearchHit = { gid: number; score: number };

/**
 * Entrées qui contiennent tous les mots : le dernier mot est un préfixe (saisie en cours), les
 * autres aussi dès qu'ils ne sont pas trouvés tels quels. Score : mots dans le titre d'abord.
 */
export function searchIndex(tokens: string[], shards: Record<string, Shard | undefined>, maxWords = 60): SearchHit[] {
  if (!tokens.length) return [];
  let result: Map<number, number> | null = null;
  tokens.forEach((token, i) => {
    const shard = shards[shardKey(token)] ?? {};
    const exact = token in shard;
    const words = exact && i < tokens.length - 1 ? [token] : Object.keys(shard).filter(w => w.startsWith(token)).sort((a, b) => a.length - b.length).slice(0, maxWords);
    const scores = new Map<number, number>();
    for (const w of words) {
      const { all, title } = decodePostings(shard[w]);
      const bonus = w === token ? 2 : 1;
      for (const id of all) scores.set(id, Math.max(scores.get(id) ?? 0, bonus));
      for (const id of title) scores.set(id, Math.max(scores.get(id) ?? 0, 10 * bonus));
    }
    if (result === null) result = scores;
    else {
      const next = new Map<number, number>();
      for (const [id, sc] of result) {
        const other = scores.get(id);
        if (other !== undefined) next.set(id, sc + other);
      }
      result = next;
    }
  });
  const final: Map<number, number> = result ?? new Map();
  return [...final.entries()].map(([gid, score]) => ({ gid, score })).sort((a, b) => b.score - a.score || a.gid - b.gid);
}

// --- liens automatiques -------------------------------------------------------------------------------

export type Segment = { text: string; ref?: string };

/**
 * Découpe `text` en segments, les noms propres connus (`names` : nom → « section/id ») devenant des
 * liens ; le plus long nom (jusqu'à `maxWords` mots) gagne, chaque cible n'est liée qu'une fois,
 * `exclude` (l'entrée affichée) jamais.
 */
export function linkNames(text: string, names: ReadonlyMap<string, string>, exclude?: string, maxWords = 5, used = new Set<string>()): Segment[] {
  if (!names.size || !text) return [{ text }];
  const words = [...text.matchAll(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu)];
  const out: Segment[] = [];
  let cursor = 0;
  for (let i = 0; i < words.length; i++) {
    for (let n = Math.min(maxWords, words.length - i); n >= 1; n--) {
      const start = words[i].index!;
      const last = words[i + n - 1];
      const end = last.index! + last[0].length;
      const candidate = text.slice(start, end);
      const ref = names.get(candidate);
      if (ref && ref !== exclude && !used.has(ref)) {
        if (start > cursor) out.push({ text: text.slice(cursor, start) });
        out.push({ text: candidate, ref });
        used.add(ref);
        cursor = end;
        i += n - 1;
        break;
      }
    }
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}

// --- liste virtualisée ---------------------------------------------------------------------------------

export type Row = { kind: 'group'; group: number; label: string; count: number } | { kind: 'entry'; index: number };

/** Lignes de la liste : en-tête de groupe puis entrées ; `groupFilter` ne garde qu'un groupe. */
export function listRows(list: ListData, label: (g: ListGroup) => string, groupFilter?: number): Row[] {
  const out: Row[] = [];
  let current = -1;
  list.rows.forEach((row, index) => {
    if (groupFilter !== undefined && row[1] !== groupFilter) return;
    if (row[1] !== current) {
      current = row[1];
      const g = list.groups[current];
      out.push({ kind: 'group', group: current, label: label(g), count: g.count });
    }
    out.push({ kind: 'entry', index });
  });
  return out;
}

export function visibleRange(scrollTop: number, viewport: number, rowHeight: number, count: number, overscan = 8): [number, number] {
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const last = Math.min(count, Math.ceil((scrollTop + viewport) / rowHeight) + overscan);
  return [first, last];
}

// --- Markdown minimal des textes communautaires ------------------------------------------------------

export type MdBlock = { type: 'h' | 'p' | 'li'; text: string };

export function parseMarkdown(md: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  let para: string[] = [];
  const flush = () => { if (para.length) { blocks.push({ type: 'p', text: para.join(' ') }); para = []; } };
  let prevLine = '';
  for (const raw of md.split('\n')) {
    const line = raw.trim();
    if (!line) { flush(); prevLine = ''; continue; }
    const h = /^#{1,6}\s+(.*)$/.exec(line);
    const li = /^[-*•]\s+(.*)$/.exec(line);
    const last = blocks[blocks.length - 1];
    if (h) { flush(); blocks.push({ type: 'h', text: h[1] }); }
    else if (li) { flush(); blocks.push({ type: 'li', text: li[1] }); }
    else if (!para.length && last?.type === 'li' && prevLine) last.text += ` ${line}`;   // suite de la puce
    else para.push(line);
    prevLine = line;
  }
  flush();
  return blocks;
}

/** Texte officiel : paragraphes séparés par une ligne vide ou un retour à la ligne. */
export function paragraphs(text: string): string[] {
  return text.split(/\n+/).map(p => p.trim()).filter(Boolean);
}
