import type {
  AxisPlacement, ClassTalents, LocText, TalentCell, TalentField, TalentInfo, TalentLang, TalentsIndex, TalentVar, VersionEntry,
} from './talents.types';

/** Ordre de repli des langues : celle du site, puis français, anglais, russe (textes du client). */
export function textFor(value: LocText | undefined, lang: TalentLang): { text: string; lang: TalentLang } | null {
  if (!value) return null;
  for (const l of [lang, 'fr', 'en', 'ru'] as TalentLang[]) {
    const t = value[l];
    if (t) return { text: t, lang: l };
  }
  return null;
}

/**
 * Nom interne tiré de la référence de la ressource, quand le client n'a pas de texte
 * (11.0 : pak de textes absent). `Mechanics/Spells/War63/Spells/PowerAttack/Spell01.xdb`
 * → `PowerAttack` ; `#2259` reste tel quel.
 */
export function internalName(ref: string): string {
  if (!ref.includes('/')) return ref;
  const parts = ref.split('/');
  const file = (parts.pop() ?? '').replace(/\..*$/, '');
  if (/^(spell|ability|buff)[\d_]*$/i.test(file) && parts.length) return parts[parts.length - 1];
  return file;
}

export function talentName(t: TalentInfo | undefined, lang: TalentLang): { text: string; lang: TalentLang | null; internal: boolean } {
  if (!t) return { text: '?', lang: null, internal: true };
  const found = textFor(t.name, lang);
  return found ? { ...found, internal: false } : { text: internalName(t.ref), lang: null, internal: true };
}

/** Valeur d'une variable `<r name="…"/>` : brute (le jeu la met en forme) et marquée si des formules s'y appliquent. */
export function formatVar(v: TalentVar | undefined, lang: TalentLang): { text: string; scaled: boolean } | null {
  if (!v || v.value === null || v.value === undefined) return null;
  const n = Math.round(v.value * 1000) / 1000;
  const text = n.toLocaleString(lang === 'fr' ? 'fr-FR' : lang === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: 3 });
  return { text, scaled: Boolean(v.scalers?.length) };
}

export type Segment =
  | { kind: 'text'; text: string; tone?: string }
  | { kind: 'var'; name: string; value: string | null; scaled: boolean; tone?: string }
  | { kind: 'br' };

const TONES: Record<string, string> = {
  tip_green: 'green', tip_blue: 'blue', tip_base: 'base', tip_red: 'red', tip_yellow: 'yellow', tip_golden: 'yellow',
  tip_white: 'white', tip_grey: 'grey', colormagenta: 'magenta', header: 'yellow',
};

/**
 * Découpe une description du jeu (HTML maison : `<tip_green>`, `<br/>`, `<r name/>`…) en
 * segments sûrs à afficher ; les balises inconnues sont retirées, leur texte conservé.
 */
export function parseGameText(src: string, vars: Record<string, TalentVar> | undefined, lang: TalentLang): Segment[] {
  const out: Segment[] = [];
  const tones: string[] = [];
  const re = /<\s*(\/?)\s*([A-Za-z_][\w-]*)([^>]*?)(\/?)\s*>/g;
  let last = 0;
  let m: RegExpExecArray | null;
  const push = (text: string) => {
    if (!text) return;
    const clean = text.replace(/\r/g, '').replace(/\n/g, ' ').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    if (clean) out.push({ kind: 'text', text: clean, tone: tones[tones.length - 1] });
  };
  while ((m = re.exec(src))) {
    push(src.slice(last, m.index));
    last = re.lastIndex;
    const [, closing, rawTag, attrs, selfClose] = m;
    const tag = rawTag.toLowerCase();
    if (tag === 'br') { out.push({ kind: 'br' }); continue; }
    if (tag === 'p' && closing && out.length) { out.push({ kind: 'br' }); continue; }
    if (tag === 'r') {
      const name = /name\s*=\s*"([^"]*)"/.exec(attrs)?.[1] ?? '';
      const f = formatVar(vars?.[name], lang);
      out.push({ kind: 'var', name, value: f?.text ?? null, scaled: f?.scaled ?? false, tone: tones[tones.length - 1] });
      continue;
    }
    if (selfClose) continue;
    const tone = TONES[tag];
    if (tone) {
      if (closing) tones.pop(); else tones.push(tone);
    }
  }
  push(src.slice(last));
  while (out.length && out[out.length - 1].kind === 'br') out.pop();
  return out;
}

/** Groupe de cases d'une grille occupées par un même talent (une case par rang). */
export type FieldGroup = { talent: string; cells: [number, number][] };

/** Composantes connexes (4-voisinage) des cases partageant la même clé de talent. */
export function fieldGroups(rows: (TalentCell | null)[][]): FieldGroup[] {
  const seen = new Set<string>();
  const groups: FieldGroup[] = [];
  rows.forEach((row, r) => row.forEach((cell, c) => {
    if (!cell || seen.has(`${r},${c}`)) return;
    const stack: [number, number][] = [[r, c]];
    const cells: [number, number][] = [];
    seen.add(`${r},${c}`);
    while (stack.length) {
      const [y, x] = stack.pop()!;
      cells.push([y, x]);
      for (const [dy, dx] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const ny = y + dy, nx = x + dx;
        const k = `${ny},${nx}`;
        if (seen.has(k) || rows[ny]?.[nx]?.talent !== cell.talent) continue;
        seen.add(k);
        stack.push([ny, nx]);
      }
    }
    cells.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    groups.push({ talent: cell.talent, cells });
  }));
  return groups;
}

/**
 * Place une grille de `rows × cols` sur le damier 9 × 9 de la fenêtre 17.0 : centrée, de
 * sorte que la case de départ (au centre dans toutes les versions lues) tombe au centre.
 * Renvoie le décalage (ligne, colonne) à ajouter.
 */
export function boardOffset(field: TalentField, size = 9): [number, number] {
  const rows = field.rows.length;
  const cols = Math.max(0, ...field.rows.map(r => r.length));
  return [Math.max(0, Math.floor((size - rows) / 2)), Math.max(0, Math.floor((size - cols) / 2))];
}

export type Prereq =
  | { kind: 'points'; points: number }
  | { kind: 'parent'; talent: string }
  | { kind: 'unlock'; ref: string }
  | { kind: 'fieldStart' }
  | { kind: 'fieldRanks'; count: number };

/** Prérequis d'une case du livre : palier de points de la couche, talent parent, déblocage. */
export function bookPrereqs(data: ClassTalents, layer: number, col: number): Prereq[] {
  const L = data.book.layers[layer];
  const cell = L?.cells[col];
  if (!cell) return [];
  const out: Prereq[] = [];
  if (L.points) out.push({ kind: 'points', points: L.points });
  if (cell.parent) out.push({ kind: 'parent', talent: cell.parent });
  if (cell.unlock ?? L.unlock) out.push({ kind: 'unlock', ref: (cell.unlock ?? L.unlock)! });
  return out;
}

/** Prérequis d'une case de grille : parent/déblocage déclarés, case de départ, nombre de cases (= rangs). */
export function fieldPrereqs(field: TalentField, r: number, c: number): Prereq[] {
  const cell = field.rows[r]?.[c];
  if (!cell) return [];
  const out: Prereq[] = [];
  if (field.start && field.start[0] === r && field.start[1] === c) out.push({ kind: 'fieldStart' });
  if (cell.parent) out.push({ kind: 'parent', talent: cell.parent });
  if (cell.unlock) out.push({ kind: 'unlock', ref: cell.unlock });
  const group = fieldGroups(field.rows).find(g => g.cells.some(([y, x]) => y === r && x === c));
  if (group && group.cells.length > 1) out.push({ kind: 'fieldRanks', count: group.cells.length });
  return out;
}

/** Choix de version/classe depuis l'URL, avec repli sur la dernière version et la première classe. */
export function resolveSelection(index: TalentsIndex, v: string | null, c: string | null): { version: VersionEntry | null; slug: string | null } {
  const versions = index.versions.filter(x => x.classes.length);
  const version = versions.find(x => x.id === v) ?? versions[versions.length - 1] ?? null;
  if (!version) return { version: null, slug: null };
  const cls = version.classes.find(x => x.slug === c) ?? version.classes[0];
  return { version, slug: cls?.slug ?? null };
}

export function talentsFile(version: string, slug: string): string {
  return `/game/talents/${version}/${slug}.json`;
}

export function iconFile(name: string): string {
  return `/game/talents/icons/${name}`;
}

/* --- placement des widgets du client (WidgetPlacement) --- */

export type Rect = { x: number; y: number; w: number; h: number };

/**
 * Position d'un axe dans le parent, selon `WidgetAlign` : LOW = `pos` depuis le bord bas
 * de l'axe (gauche/haut), taille `size` ; HIGH = `high` depuis le bord haut (droite/bas) ;
 * CENTER = centré puis décalé de `pos` ; BOTH = étiré entre `pos` et `high`.
 */
export function placeAxis(p: AxisPlacement, parent: number): [number, number] {
  const pos = p.pos ?? 0, high = p.high ?? 0, size = p.size ?? 0;
  switch (p.align) {
    case 'high': return [parent - high - size, size];
    case 'center': return [(parent - size) / 2 + pos, size];
    case 'both': return [pos, parent - pos - high];
    default: return [pos, size || Math.max(0, parent - pos - high)];
  }
}

export function placeWidget(place: { x: AxisPlacement; y: AxisPlacement }, parentW: number, parentH: number): Rect {
  const [x, w] = placeAxis(place.x, parentW);
  const [y, h] = placeAxis(place.y, parentH);
  return { x, y, w, h };
}
