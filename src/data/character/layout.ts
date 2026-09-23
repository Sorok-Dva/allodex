/**
 * Placement des widgets du client (`WidgetPlacement`) : sur chaque axe, un alignement et
 * trois nombres — `pos` (décalage depuis le bord bas/gauche ou le centre), `high` (décalage
 * depuis le bord haut/droit), `size`. `both` étire entre les deux bords.
 */
import type { Axis, GameText, UiWidget } from './chargen.types';
import type { Lang } from '@/lib/i18n/messages';

export type Rect = { x: number; y: number; w: number; h: number };

export function placeAxis(axis: Axis, parent: number): [number, number] {
  const pos = axis.pos ?? 0;
  const high = axis.high ?? 0;
  const size = axis.size ?? 0;
  switch (axis.align) {
    case 'high': return [parent - high - size, size];
    // Taille nulle centrée : le texte s'ajuste à son contenu dans le client ; on occupe tout le parent.
    case 'center': return size ? [(parent - size) / 2 + pos, size] : [pos, parent];
    case 'both': return [pos, Math.max(0, parent - pos - high)];
    default: return [pos, size];
  }
}

export function placeWidget(w: Pick<UiWidget, 'place'>, pw: number, ph: number): Rect {
  const [x, width] = placeAxis(w.place.x, pw);
  const [y, height] = placeAxis(w.place.y, ph);
  return { x, y, w: width, h: height };
}

export function findWidget(root: UiWidget, ...path: string[]): UiWidget | null {
  let node: UiWidget | null = root;
  for (const name of path) {
    node = node?.children?.find(c => c.name === name) ?? null;
    if (!node) return null;
  }
  return node;
}

/** Ordre de tracé du client : priorité croissante, ordre du fichier à égalité. */
export function byPriority(list: UiWidget[] | undefined): UiWidget[] {
  return (list ?? []).map((w, i) => ({ w, i })).sort((a, b) => a.w.priority - b.w.priority || a.i - b.i).map(x => x.w);
}

/** Échelle de l'interface : le jeu dessine en pixels ; sous 1080 px de haut, on réduit tout. */
export function uiScale(width: number, height: number): number {
  return Math.min(1, height / 1080, width / 1500);
}

export type TextLang = Lang | 'ru';

/** Texte du client dans la langue voulue : la langue, puis l'anglais, puis le russe. */
export function gameText(value: GameText | null | undefined, lang: TextLang): string {
  if (!value) return '';
  return value[lang] ?? value.en ?? value.ru ?? value.fr ?? '';
}

export type Span = { text: string; cls?: string; br?: boolean };

/**
 * Balisage des textes du client (`<html><tip_white>Тип брони:</tip_white> …<br/></html>`,
 * `<header>`, `<p>`) → segments à styler ; les balises inconnues sont ignorées, les
 * variables `<r name="x"/>` remplacées par `vars[x]`.
 */
export function parseGameMarkup(src: string, vars: Record<string, string | number> = {}): Span[] {
  const out: Span[] = [];
  const stack: string[] = [];
  const re = /<\/?([a-zA-Z_]+)[^>]*?\/?>|([^<]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    if (m[2] !== undefined) {
      const text = m[2].replace(/\r?\n/g, ' ');
      if (text.trim() || text === ' ') out.push({ text, cls: stack[stack.length - 1] });
      continue;
    }
    const tag = m[1].toLowerCase();
    const whole = m[0];
    if (tag === 'br' || (tag === 'p' && whole.startsWith('</'))) { out.push({ text: '', br: true }); continue; }
    if (tag === 'r') {
      const name = /name\s*=\s*"([^"]+)"/.exec(whole)?.[1];
      if (name && name in vars) out.push({ text: String(vars[name]), cls: stack[stack.length - 1] });
      continue;
    }
    if (whole.startsWith('</')) { const i = stack.lastIndexOf(tag); if (i >= 0) stack.splice(i, 1); continue; }
    if (whole.endsWith('/>')) continue;
    if (tag.startsWith('tip_') || tag === 'header') stack.push(tag);
  }
  return out;
}
