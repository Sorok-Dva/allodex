import type { ClassTalents, TalentField, TalentsIndex } from './talents.types';

/**
 * Calculateur de build : règles du livre et des grilles, telles que les applique le script
 * `ClassBuild`/`ClassState` de l'addon `TalentBuilder` du client 17.0 (bytecode lu et
 * documenté dans le README, section « Calculateur »), et codage versionné pour l'URL.
 *
 * - Livre : le rang `r` d'un sort coûte `rankCost[r-1]` points (1, 2, 3) ; une couche n'est
 *   accessible que si les couches précédentes totalisent son palier (`layers[i].points`) ; un
 *   sort qui a un parent ne peut pas dépasser le rang de ce parent. Retirer un rang propage :
 *   les rangs devenus hors palier ou supérieurs à leur parent retombent (comme le recalcul du jeu).
 * - Grilles : une case (= un rang du talent qui l'occupe) coûte 1 point et ne s'apprend que si
 *   elle touche (4-voisinage) une case apprise reliée à la case de départ, ou la case de départ.
 *   Retirer une case retire celles qui ne sont plus reliées au départ.
 */

export type VersionRules = {
  /** Points du livre au-delà des rangs de départ ; `null` = total inconnu, pas de plafond. */
  bookPoints: number | null;
  /** Points des grilles au-delà des cases de départ ; `null` = inconnu. */
  fieldPoints: number | null;
  /** La première couche du livre est apprise d'office au rang 1 (sorts de départ). */
  bookStartRank: boolean;
  /** Coût des rangs 1, 2, 3 du livre (`ClassBuild`, table littérale `{1, 2, 3}`). */
  rankCost: number[];
};

const DEFAULT_RULES: VersionRules = { bookPoints: null, fieldPoints: null, bookStartRank: true, rankCost: [1, 2, 3] };

/** Totaux d'une version, tels que l'index les tient du manifeste (`points`, avec leur source). */
export type VersionPoints = { book: number; field: number; source?: string };

/**
 * Règles d'une version. Les totaux de points ne sont pas dans les données du client (le serveur
 * les accorde au fil des niveaux) : ils viennent de `tools/talents_manifest.json` (`points`),
 * recopiés dans l'index ; sans eux, pas de plafond. La première couche du livre est offerte au
 * rang 1 dans toutes les versions ; le script 17.0 le confirme (compteur « − 3 »).
 */
export function rulesFor(points?: VersionPoints | null, rankCost?: number[]): VersionRules {
  return {
    ...DEFAULT_RULES,
    ...(rankCost?.length ? { rankCost } : {}),
    ...(points ? { bookPoints: points.book, fieldPoints: points.field } : {}),
  };
}

export type Build = {
  /** Rang de chaque emplacement du livre, [couche][colonne]. */
  book: number[][];
  /** Cases apprises de chaque grille, [grille][ligne][colonne]. */
  fields: boolean[][][];
};

export type Calc = { data: ClassTalents; rules: VersionRules };

export const BOOK_COLS = 4;

/* --- livre ------------------------------------------------------------------------------ */

export function bookCell(data: ClassTalents, r: number, c: number) {
  return data.book.layers[r]?.cells[c] ?? null;
}

export function maxRank(data: ClassTalents, r: number, c: number): number {
  const cell = bookCell(data, r, c);
  if (!cell) return 0;
  return Math.max(1, data.talents[cell.talent]?.ranks.length ?? 1);
}

export function minRank(calc: Calc, r: number, c: number): number {
  return calc.rules.bookStartRank && r === 0 && bookCell(calc.data, r, c) ? 1 : 0;
}

/** Points cumulés pour atteindre le rang `rank`. */
export function rankTotal(rules: VersionRules, rank: number): number {
  let sum = 0;
  for (let i = 0; i < rank; i++) sum += rules.rankCost[Math.min(i, rules.rankCost.length - 1)] ?? 1;
  return sum;
}

/** Points dépensés dans les couches avant `row` (rangs de départ compris, comme le jeu). */
export function spentBeforeRow(calc: Calc, build: Build, row: number): number {
  let sum = 0;
  for (let r = 0; r < row; r++) for (const rank of build.book[r] ?? []) sum += rankTotal(calc.rules, rank);
  return sum;
}

export function bookSpent(calc: Calc, build: Build): number {
  let sum = 0;
  build.book.forEach((row, r) => row.forEach((rank, c) => { sum += rankTotal(calc.rules, rank) - rankTotal(calc.rules, minRank(calc, r, c)); }));
  return sum;
}

function bookPosition(data: ClassTalents, talent: string): [number, number] | null {
  for (let r = 0; r < data.book.layers.length; r++) {
    const c = data.book.layers[r].cells.findIndex(x => x?.talent === talent);
    if (c >= 0) return [r, c];
  }
  return null;
}

export type BookBlock = 'empty' | 'max' | 'threshold' | 'parent' | 'points';

/** Raison pour laquelle le rang suivant ne peut pas être pris (null = possible). */
export function bookBlock(calc: Calc, build: Build, r: number, c: number): BookBlock | null {
  const cell = bookCell(calc.data, r, c);
  if (!cell) return 'empty';
  const rank = build.book[r][c];
  if (rank >= maxRank(calc.data, r, c)) return 'max';
  if (spentBeforeRow(calc, build, r) < (calc.data.book.layers[r].points ?? 0)) return 'threshold';
  if (cell.parent) {
    const p = bookPosition(calc.data, cell.parent);
    if (p && build.book[p[0]][p[1]] <= rank) return 'parent';
  }
  const budget = calc.rules.bookPoints;
  if (budget !== null && bookSpent(calc, build) + rankTotal(calc.rules, rank + 1) - rankTotal(calc.rules, rank) > budget) return 'points';
  return null;
}

/* --- grilles ---------------------------------------------------------------------------- */

export function fieldCols(field: TalentField): number {
  return Math.max(0, ...field.rows.map(r => r.length));
}

/** Case de départ : déclarée par la ressource, sinon le centre (toutes les versions lues). */
export function fieldStart(field: TalentField): [number, number] {
  return field.start ?? [Math.floor(field.rows.length / 2), Math.floor(fieldCols(field) / 2)];
}

function hasCell(field: TalentField, r: number, c: number): boolean {
  return Boolean(field.rows[r]?.[c]);
}

/** La case de départ porte un talent : il est appris d'office (gratuit). */
export function autoStart(field: TalentField): boolean {
  const [r, c] = fieldStart(field);
  return hasCell(field, r, c);
}

const NEIGHBOURS: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1]];

/** Cases apprises reliées au départ (le départ vide sert d'ancre). */
export function connected(field: TalentField, learned: boolean[][]): Set<string> {
  const [sr, sc] = fieldStart(field);
  const seen = new Set<string>([`${sr},${sc}`]);
  const stack: [number, number][] = [[sr, sc]];
  while (stack.length) {
    const [r, c] = stack.pop()!;
    for (const [dr, dc] of NEIGHBOURS) {
      const nr = r + dr, nc = c + dc, k = `${nr},${nc}`;
      if (seen.has(k) || !learned[nr]?.[nc]) continue;
      seen.add(k);
      stack.push([nr, nc]);
    }
  }
  return seen;
}

export function fieldSpent(calc: Calc, build: Build): number {
  let sum = 0;
  calc.data.fields.forEach((field, f) => {
    const [sr, sc] = fieldStart(field);
    (build.fields[f] ?? []).forEach((row, r) => row.forEach((on, c) => {
      if (on && !(r === sr && c === sc && autoStart(field))) sum += 1;
    }));
  });
  return sum;
}

export type FieldBlock = 'empty' | 'learned' | 'isolated' | 'points';

export function fieldBlock(calc: Calc, build: Build, f: number, r: number, c: number): FieldBlock | null {
  const field = calc.data.fields[f];
  if (!field || !hasCell(field, r, c)) return 'empty';
  const learned = build.fields[f];
  if (learned[r][c]) return 'learned';
  const reach = connected(field, learned);
  if (!NEIGHBOURS.some(([dr, dc]) => reach.has(`${r + dr},${c + dc}`))) return 'isolated';
  const budget = calc.rules.fieldPoints;
  if (budget !== null && fieldSpent(calc, build) + 1 > budget) return 'points';
  return null;
}

/** Rang atteint par un talent de grille : cases apprises / cases qu'il occupe dans la grille. */
export function fieldTalentRank(field: TalentField, learned: boolean[][], talent: string): { current: number; total: number } {
  let current = 0, total = 0;
  field.rows.forEach((row, r) => row.forEach((cell, c) => {
    if (cell?.talent !== talent) return;
    total += 1;
    if (learned[r]?.[c]) current += 1;
  }));
  return { current, total };
}

/* --- état ------------------------------------------------------------------------------- */

export function emptyBuild(calc: Calc): Build {
  const book = calc.data.book.layers.map((layer, r) => Array.from({ length: BOOK_COLS }, (_, c) => (layer.cells[c] ? minRank(calc, r, c) : 0)));
  const fields = calc.data.fields.map(field => {
    const cols = fieldCols(field);
    const [sr, sc] = fieldStart(field);
    const auto = autoStart(field);
    return field.rows.map((_, r) => Array.from({ length: cols }, (_, c) => auto && r === sr && c === sc));
  });
  return { book, fields };
}

function clone(build: Build): Build {
  return { book: build.book.map(r => [...r]), fields: build.fields.map(f => f.map(r => [...r])) };
}

/**
 * Recalcul du jeu après un retrait : rangs hors palier ou au-dessus de leur parent ramenés,
 * cases de grille détachées du départ retirées. Idempotent ; un build valide est inchangé.
 */
export function normalize(calc: Calc, input: Build): Build {
  const build = clone(input);
  const { data } = calc;
  for (let guard = 0; guard < 64; guard++) {
    let changed = false;
    let before = 0;
    data.book.layers.forEach((layer, r) => {
      let rowSum = 0;
      for (let c = 0; c < BOOK_COLS; c++) {
        const cell = layer.cells[c];
        const min = minRank(calc, r, c);
        let rank = cell ? Math.min(build.book[r][c], maxRank(data, r, c)) : 0;
        if (rank > min && before < (layer.points ?? 0)) rank = min;
        if (cell?.parent && rank > min) {
          const p = bookPosition(data, cell.parent);
          if (p && build.book[p[0]][p[1]] < rank) rank = Math.max(min, build.book[p[0]][p[1]]);
        }
        rank = Math.max(rank, min);
        if (rank !== build.book[r][c]) { build.book[r][c] = rank; changed = true; }
        rowSum += rankTotal(calc.rules, rank);
      }
      before += rowSum;
    });
    if (!changed) break;
  }
  data.fields.forEach((field, f) => {
    const learned = build.fields[f];
    const [sr, sc] = fieldStart(field);
    if (autoStart(field)) learned[sr][sc] = true;
    const reach = connected(field, learned);
    learned.forEach((row, r) => row.forEach((on, c) => {
      if (on && (!hasCell(field, r, c) || !reach.has(`${r},${c}`))) row[c] = false;
    }));
  });
  return build;
}

/** Prend le rang suivant (ou tous les rangs possibles avec `full`) ; null si impossible. */
export function addBook(calc: Calc, build: Build, r: number, c: number, full = false): Build | null {
  if (bookBlock(calc, build, r, c)) return null;
  let next = clone(build);
  do {
    next.book[r][c] += 1;
  } while (full && !bookBlock(calc, next, r, c));
  next = normalize(calc, next);
  return next;
}

export function removeBook(calc: Calc, build: Build, r: number, c: number, full = false): Build | null {
  const min = minRank(calc, r, c);
  if (build.book[r]?.[c] === undefined || build.book[r][c] <= min) return null;
  const next = clone(build);
  next.book[r][c] = full ? min : next.book[r][c] - 1;
  return normalize(calc, next);
}

/** Apprend une case ; avec `same`, toutes les cases du même talent devenues accessibles. */
export function addField(calc: Calc, build: Build, f: number, r: number, c: number, same = false): Build | null {
  if (fieldBlock(calc, build, f, r, c)) return null;
  const next = clone(build);
  next.fields[f][r][c] = true;
  const talent = calc.data.fields[f].rows[r][c]!.talent;
  if (same) {
    for (let found = true; found;) {
      found = false;
      calc.data.fields[f].rows.forEach((row, y) => row.forEach((cell, x) => {
        if (cell?.talent === talent && !fieldBlock(calc, next, f, y, x)) { next.fields[f][y][x] = true; found = true; }
      }));
    }
  }
  return next;
}

export function removeField(calc: Calc, build: Build, f: number, r: number, c: number, same = false): Build | null {
  const field = calc.data.fields[f];
  if (!field || !build.fields[f]?.[r]?.[c]) return null;
  const [sr, sc] = fieldStart(field);
  const isStart = (y: number, x: number) => autoStart(field) && y === sr && x === sc;
  if (isStart(r, c)) return null;
  const next = clone(build);
  const talent = field.rows[r][c]!.talent;
  next.fields[f][r][c] = false;
  if (same) field.rows.forEach((row, y) => row.forEach((cell, x) => { if (cell?.talent === talent && !isStart(y, x)) next.fields[f][y][x] = false; }));
  return normalize(calc, next);
}

/* --- codage pour l'URL ------------------------------------------------------------------ */

/**
 * `b=<format>.<livre>.<grille 1>.<grille 2>.<grille 3>` (la version et la classe sont dans
 * `v` et `c`) :
 * - format : `1` ;
 * - livre : un chiffre par emplacement (rang), couche après couche, 4 par couche, zéros de
 *   fin retirés ;
 * - grille : cases apprises en base64url (A–Z a–z 0–9 - _), 6 cases par caractère, bit de
 *   poids faible d'abord, ligne après ligne sur la largeur de la grille, `A` de fin retirés ;
 *   la case de départ apprise d'office n'est pas codée (implicite).
 * Segments vides de fin retirés. Un build vide (état de départ) n'a pas de code.
 */
export const BUILD_FORMAT = '1';
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

function sameBuild(a: Build, b: Build): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function encodeBuild(calc: Calc, build: Build): string | null {
  if (sameBuild(build, emptyBuild(calc))) return null;
  const book = build.book.flat().join('').replace(/0+$/, '');
  const grids = calc.data.fields.map((field, f) => {
    const cols = fieldCols(field);
    const [sr, sc] = fieldStart(field);
    const auto = autoStart(field);
    const bits: number[] = [];
    field.rows.forEach((_, r) => { for (let c = 0; c < cols; c++) bits.push(build.fields[f]?.[r]?.[c] && !(auto && r === sr && c === sc) ? 1 : 0); });
    let out = '';
    for (let i = 0; i < bits.length; i += 6) {
      let v = 0;
      for (let k = 0; k < 6; k++) v |= (bits[i + k] ?? 0) << k;
      out += B64[v];
    }
    return out.replace(/A+$/, '');
  });
  return [BUILD_FORMAT, book, ...grids].join('.').replace(/\.+$/, '');
}

export type DecodeError = 'format' | 'syntax' | 'book' | 'grid' | 'rules' | 'points';
export type Decoded = { ok: true; build: Build } | { ok: false; error: DecodeError };

export function decodeBuild(calc: Calc, code: string): Decoded {
  const parts = code.split('.');
  if (parts[0] !== BUILD_FORMAT) return { ok: false, error: 'format' };
  const nFields = calc.data.fields.length;
  if (parts.length > 2 + nFields) return { ok: false, error: 'syntax' };
  const bookCode = parts[1] ?? '';
  if (!/^[0-9]*$/.test(bookCode)) return { ok: false, error: 'syntax' };
  const layers = calc.data.book.layers.length;
  if (bookCode.length > layers * BOOK_COLS) return { ok: false, error: 'book' };
  const build = emptyBuild(calc);
  for (let r = 0; r < layers; r++) {
    for (let c = 0; c < BOOK_COLS; c++) {
      const rank = Number(bookCode[r * BOOK_COLS + c] ?? '0');
      if (rank > maxRank(calc.data, r, c)) return { ok: false, error: 'book' };
      if (rank < minRank(calc, r, c)) return { ok: false, error: 'rules' };
      build.book[r][c] = rank;
    }
  }
  for (let f = 0; f < nFields; f++) {
    const field = calc.data.fields[f];
    const g = parts[2 + f] ?? '';
    if (!/^[A-Za-z0-9_-]*$/.test(g)) return { ok: false, error: 'syntax' };
    const cols = fieldCols(field);
    const total = field.rows.length * cols;
    const [sr, sc] = fieldStart(field);
    const auto = autoStart(field);
    if (g.length > Math.ceil(total / 6)) return { ok: false, error: 'grid' };
    for (let i = 0; i < g.length * 6; i++) {
      const on = Boolean((B64.indexOf(g[Math.floor(i / 6)]) >> (i % 6)) & 1);
      if (!on) continue;
      const r = Math.floor(i / cols), c = i % cols;
      // Bit au-delà de la dernière case, sur une case vide, ou sur le départ (implicite).
      if (i >= total || !hasCell(field, r, c) || (auto && r === sr && c === sc)) return { ok: false, error: 'grid' };
      build.fields[f][r][c] = true;
    }
  }
  if (!sameBuild(normalize(calc, build), build)) return { ok: false, error: 'rules' };
  const { bookPoints, fieldPoints } = calc.rules;
  if ((bookPoints !== null && bookSpent(calc, build) > bookPoints) || (fieldPoints !== null && fieldSpent(calc, build) > fieldPoints)) {
    return { ok: false, error: 'points' };
  }
  return { ok: true, build };
}

/**
 * Un build partagé ne vaut que pour la version et la classe exactes de son lien : pas de
 * repli sur une autre version (les grilles changent d'une version à l'autre).
 */
export function checkShared(index: TalentsIndex, v: string | null, c: string | null): 'version' | 'class' | null {
  const version = index.versions.find(x => x.id === v && x.classes.length);
  if (!version) return 'version';
  return version.classes.some(x => x.slug === c) ? null : 'class';
}

/* --- deux builds (I et II) -------------------------------------------------------------- */

/**
 * Le jeu garde deux builds par personnage (sélecteur I / II) ; le lien les porte tous deux :
 * `b` (build I) et `b2` (build II), chacun au format ci-dessus, et `s=2` quand le build II est
 * affiché. Un ancien lien à un seul build (`b`) reste valable.
 */
export type Builds = [Build, Build];
export type SharedBuilds = { builds: Builds; errors: [DecodeError | null, DecodeError | null] };

export function encodeBuilds(calc: Calc, builds: Builds): { b: string | null; b2: string | null } {
  return { b: encodeBuild(calc, builds[0]), b2: encodeBuild(calc, builds[1]) };
}

export function decodeBuilds(calc: Calc, b: string | null, b2: string | null): SharedBuilds {
  const one = (code: string | null): [Build, DecodeError | null] => {
    if (!code) return [emptyBuild(calc), null];
    const d = decodeBuild(calc, code);
    return d.ok ? [d.build, null] : [emptyBuild(calc), d.error];
  };
  const [first, e1] = one(b);
  const [second, e2] = one(b2);
  return { builds: [first, second], errors: [e1, e2] };
}

/* --- liens sort ↔ rubis ----------------------------------------------------------------- */

/**
 * Talents liés à `talent` : les sorts qu'il modifie (`links`, 17.0) et, en retour, les talents
 * qui le modifient — ce que le jeu surligne au survol (`CalcTalentLinkedResources` marque les
 * deux sens). Le talent lui-même n'y est pas.
 */
export function linkedTalents(data: ClassTalents, talent: string): Set<string> {
  const out = new Set<string>(data.talents[talent]?.links ?? []);
  for (const [key, t] of Object.entries(data.talents)) if (t.links?.includes(talent)) out.add(key);
  out.delete(talent);
  return out;
}
