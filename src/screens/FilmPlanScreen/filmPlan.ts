/**
 * Plan du film des cinématiques (`tools/film_plan.json`) : modèle, validation et logique de la
 * page de développement `/dev/film`.
 *
 * Le fichier est la seule source de vérité, éditée de deux façons : par la page (en
 * développement, le greffon Vite `tools/vite/filmPlanPlugin.ts` l'enregistre) et par un agent
 * qui l'édite directement. Ce module est pur (ni DOM ni Node) : le greffon l'importe pour
 * valider ce qu'il écrit, la page pour tout le reste.
 *
 * Le plan ne touche pas au manifeste du film (`tools/cinematics_manifest.json`) : passer une
 * scène en production reste une étape séparée.
 */

export const PLAN_FORMAT = 1;

export type PlanFaction = 'league' | 'empire' | 'common';
export type PlanKind = 'video' | 'engine' | 'free';
/** `film` : dans le film ; `pending` : recréée ou extraite, gardée hors du film ; `todo` : à recréer. */
export type PlanStatus = 'film' | 'pending' | 'todo' | 'discarded';
export type PlanPriority = 'high' | 'medium' | 'low' | 'none';
export type PlanImportance = 'epic' | 'faction' | 'chapter-end' | 'major-event' | 'side' | 'bonus';
export type PlanVoice = 'ru' | 'none' | 'unknown';
export type PlanSubtitles = 'official' | 'partial' | 'none' | 'unknown';

export const FACTIONS: readonly PlanFaction[] = ['league', 'empire', 'common'];
export const KINDS: readonly PlanKind[] = ['video', 'engine', 'free'];
export const STATUSES: readonly PlanStatus[] = ['film', 'pending', 'todo', 'discarded'];
export const PRIORITIES: readonly PlanPriority[] = ['high', 'medium', 'low', 'none'];
export const IMPORTANCES: readonly PlanImportance[] = ['epic', 'faction', 'chapter-end', 'major-event', 'side', 'bonus'];
const VOICES: readonly PlanVoice[] = ['ru', 'none', 'unknown'];
const SUBTITLES: readonly PlanSubtitles[] = ['official', 'partial', 'none', 'unknown'];

/** Un chapitre de l'histoire (frise A → Z) ; un chapitre sans scène « dans le film » est un trou. */
export type PlanChapter = {
  id: string;
  title: string;
  version: string;
  faction: PlanFaction;
  summary?: string;
  /** D'où vient ce chapitre (intrigues des quêtes de l'arbre 7.0, registre vidéo…). */
  source?: string;
};

export type PlanEntry = {
  id: string;
  title: string;
  chapter: string;
  faction: PlanFaction;
  zone: string;
  version: string;
  kind: PlanKind;
  /** Durée en secondes ; `null` = inconnue. */
  duration: number | null;
  /** Durée estimée (voix, buffs) et non mesurée sur un chapitre existant. */
  durationEstimated?: boolean;
  status: PlanStatus;
  priority: PlanPriority;
  /** Priorité proposée par l'inventaire, pas encore décidée par l'utilisateur. */
  priorityProposed?: boolean;
  importance?: PlanImportance;
  voice?: PlanVoice;
  subtitles?: PlanSubtitles;
  /** Quête, zone de script ou événement qui déclenche la scène. */
  trigger?: string;
  /** Ressources qui attestent la scène (chemins de l'arbre 7.0, identifiants du 17.0…). */
  source?: string;
  /** Identifiant du chapitre de `/cinematics`, s'il existe. */
  siteChapter?: string | null;
  /** Chapitre bonus (joué après la fin du film) : hors des totaux. */
  bonus?: boolean;
  note?: string;
};

export type FilmPlan = {
  _note?: string;
  format: number;
  /** Durée visée d'un film de faction, en minutes. */
  targetMinutes: number;
  chapters: PlanChapter[];
  entries: PlanEntry[];
};

export const STATUS_LABEL: Record<PlanStatus, string> = {
  film: 'Dans le film', pending: 'En attente', todo: 'À recréer', discarded: 'Écartée',
};
export const PRIORITY_LABEL: Record<PlanPriority, string> = {
  high: 'Haute', medium: 'Moyenne', low: 'Basse', none: 'Aucune',
};
export const KIND_LABEL: Record<PlanKind, string> = { video: 'Vidéo', engine: 'Moteur 3D', free: 'Entrée libre' };
export const FACTION_LABEL: Record<PlanFaction, string> = { league: 'Ligue', empire: 'Empire', common: 'Commune' };
export const IMPORTANCE_LABEL: Record<PlanImportance, string> = {
  epic: 'Quête épique', faction: 'Chapitre de faction', 'chapter-end': 'Fin de chapitre',
  'major-event': 'Événement majeur', side: 'Secondaire', bonus: 'Bonus',
};

// --- validation ---------------------------------------------------------------------------------

const ID = /^[a-z0-9][a-z0-9._-]{0,79}$/;
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown, max = 4000): v is string => typeof v === 'string' && v.length <= max;
const inList = <T extends string>(list: readonly T[], v: unknown): v is T => typeof v === 'string' && (list as readonly string[]).includes(v);

const CHAPTER_KEYS = new Set(['id', 'title', 'version', 'faction', 'summary', 'source']);
const ENTRY_KEYS = new Set(['id', 'title', 'chapter', 'faction', 'zone', 'version', 'kind', 'duration', 'durationEstimated',
  'status', 'priority', 'priorityProposed', 'importance', 'voice', 'subtitles', 'trigger', 'source', 'siteChapter', 'bonus', 'note']);

/**
 * Vérifie un plan (structure, énumérations, identifiants uniques, chapitres référencés). Renvoie
 * la liste des erreurs, vide si le plan est valide. Le greffon Vite refuse d'écrire un plan
 * invalide ; les tests passent le fichier du dépôt par ici.
 */
export function validatePlan(data: unknown): string[] {
  const errors: string[] = [];
  if (!isObj(data)) return ['le plan doit être un objet JSON'];
  if (data.format !== PLAN_FORMAT) errors.push(`format attendu : ${PLAN_FORMAT}`);
  if (typeof data.targetMinutes !== 'number' || !(data.targetMinutes > 0 && data.targetMinutes < 1000)) errors.push('targetMinutes : nombre de minutes (0 à 1000)');
  if (data._note !== undefined && !isStr(data._note, 20000)) errors.push('_note : texte');
  for (const key of Object.keys(data)) if (!['_note', 'format', 'targetMinutes', 'chapters', 'entries'].includes(key)) errors.push(`clé inconnue : ${key}`);
  if (!Array.isArray(data.chapters)) { errors.push('chapters : liste attendue'); return errors; }
  if (!Array.isArray(data.entries)) { errors.push('entries : liste attendue'); return errors; }
  if (data.chapters.length > 500 || data.entries.length > 5000) errors.push('plan trop grand');

  const chapterIds = new Set<string>();
  data.chapters.forEach((c: unknown, i: number) => {
    const at = `chapters[${i}]`;
    if (!isObj(c)) { errors.push(`${at} : objet attendu`); return; }
    if (!isStr(c.id) || !ID.test(c.id)) errors.push(`${at}.id : identifiant (a-z, 0-9, . _ -)`);
    else if (chapterIds.has(c.id)) errors.push(`${at}.id : doublon « ${c.id} »`);
    else chapterIds.add(c.id);
    if (!isStr(c.title, 200) || !c.title.trim()) errors.push(`${at}.title : texte requis`);
    if (!isStr(c.version, 40)) errors.push(`${at}.version : texte`);
    if (!inList(FACTIONS, c.faction)) errors.push(`${at}.faction : ${FACTIONS.join(' | ')}`);
    for (const k of ['summary', 'source'] as const) if (c[k] !== undefined && !isStr(c[k])) errors.push(`${at}.${k} : texte`);
    for (const k of Object.keys(c)) if (!CHAPTER_KEYS.has(k)) errors.push(`${at} : clé inconnue ${k}`);
  });

  const entryIds = new Set<string>();
  data.entries.forEach((e: unknown, i: number) => {
    const at = `entries[${i}]`;
    if (!isObj(e)) { errors.push(`${at} : objet attendu`); return; }
    if (!isStr(e.id) || !ID.test(e.id)) errors.push(`${at}.id : identifiant (a-z, 0-9, . _ -)`);
    else if (entryIds.has(e.id)) errors.push(`${at}.id : doublon « ${e.id} »`);
    else entryIds.add(e.id);
    if (!isStr(e.title, 200) || !e.title.trim()) errors.push(`${at}.title : texte requis`);
    if (!isStr(e.chapter) || !chapterIds.has(e.chapter)) errors.push(`${at}.chapter : chapitre inconnu « ${String(e.chapter)} »`);
    if (!inList(FACTIONS, e.faction)) errors.push(`${at}.faction : ${FACTIONS.join(' | ')}`);
    if (!isStr(e.zone, 200)) errors.push(`${at}.zone : texte`);
    if (!isStr(e.version, 40)) errors.push(`${at}.version : texte`);
    if (!inList(KINDS, e.kind)) errors.push(`${at}.kind : ${KINDS.join(' | ')}`);
    if (e.duration !== null && !(typeof e.duration === 'number' && Number.isFinite(e.duration) && e.duration >= 0 && e.duration < 36000)) errors.push(`${at}.duration : secondes ou null`);
    if (!inList(STATUSES, e.status)) errors.push(`${at}.status : ${STATUSES.join(' | ')}`);
    if (!inList(PRIORITIES, e.priority)) errors.push(`${at}.priority : ${PRIORITIES.join(' | ')}`);
    if (e.importance !== undefined && !inList(IMPORTANCES, e.importance)) errors.push(`${at}.importance : ${IMPORTANCES.join(' | ')}`);
    if (e.voice !== undefined && !inList(VOICES, e.voice)) errors.push(`${at}.voice : ${VOICES.join(' | ')}`);
    if (e.subtitles !== undefined && !inList(SUBTITLES, e.subtitles)) errors.push(`${at}.subtitles : ${SUBTITLES.join(' | ')}`);
    for (const k of ['durationEstimated', 'priorityProposed', 'bonus'] as const) if (e[k] !== undefined && typeof e[k] !== 'boolean') errors.push(`${at}.${k} : booléen`);
    for (const k of ['trigger', 'source', 'note'] as const) if (e[k] !== undefined && !isStr(e[k])) errors.push(`${at}.${k} : texte (4000 caractères au plus)`);
    if (e.siteChapter !== undefined && e.siteChapter !== null && !(isStr(e.siteChapter, 80) && ID.test(e.siteChapter))) errors.push(`${at}.siteChapter : identifiant ou null`);
    for (const k of Object.keys(e)) if (!ENTRY_KEYS.has(k)) errors.push(`${at} : clé inconnue ${k}`);
  });
  return errors;
}

/** Texte du fichier : JSON indenté de deux espaces, fin de ligne finale (diffs lisibles). */
export const serializePlan = (plan: FilmPlan) => `${JSON.stringify(plan, null, 2)}\n`;

// --- frise ---------------------------------------------------------------------------------------

export type View = PlanFaction | 'all';

/** Une entrée est dans le film d'une faction si elle lui appartient ou si elle est commune. */
export const inView = (faction: PlanFaction, view: View) => view === 'all' || faction === 'common' || faction === view;

export type Filters = {
  statuses: readonly PlanStatus[];
  kind: PlanKind | 'all';
  priority: PlanPriority | 'all';
  text: string;
  gapsOnly: boolean;
};

export const DEFAULT_FILTERS: Filters = { statuses: STATUSES, kind: 'all', priority: 'all', text: '', gapsOnly: false };

const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

export function matches(entry: PlanEntry, filters: Filters): boolean {
  if (!filters.statuses.includes(entry.status)) return false;
  if (filters.kind !== 'all' && entry.kind !== filters.kind) return false;
  if (filters.priority !== 'all' && entry.priority !== filters.priority) return false;
  const text = fold(filters.text.trim());
  if (!text) return true;
  return [entry.title, entry.zone, entry.version, entry.trigger, entry.note, entry.source, entry.id]
    .some(v => v && fold(v).includes(text));
}

export type Gap = 'none' | 'partial' | 'empty';

export type ChapterView = {
  chapter: PlanChapter;
  /** Entrées du chapitre dans l'ordre du plan (visibles dans la vue, avant filtres). */
  all: PlanEntry[];
  /** Entrées qui passent les filtres. */
  shown: PlanEntry[];
  /**
   * `empty` : aucune scène connue ; `partial` : des scènes connues, aucune dans le film ;
   * `none` : au moins une scène dans le film.
   */
  gap: Gap;
  /** Durée dans le film (s). */
  filmSeconds: number;
};

export function gapOf(entries: readonly PlanEntry[]): Gap {
  const live = entries.filter(e => e.status !== 'discarded');
  if (entries.some(e => e.status === 'film' && !e.bonus)) return 'none';
  return live.length ? 'partial' : 'empty';
}

/** Frise d'une vue : chapitres de la vue dans l'ordre du plan, avec leurs entrées. */
export function timeline(plan: FilmPlan, view: View, filters: Filters = DEFAULT_FILTERS): ChapterView[] {
  const byChapter = new Map<string, PlanEntry[]>();
  for (const e of plan.entries) {
    if (!inView(e.faction, view)) continue;
    const list = byChapter.get(e.chapter) ?? [];
    list.push(e);
    byChapter.set(e.chapter, list);
  }
  const out: ChapterView[] = [];
  for (const chapter of plan.chapters) {
    if (!inView(chapter.faction, view)) continue;
    const all = byChapter.get(chapter.id) ?? [];
    const gap = gapOf(all);
    if (filters.gapsOnly && gap === 'none') continue;
    const shown = all.filter(e => matches(e, filters));
    const filmSeconds = all.reduce((sum, e) => sum + (e.status === 'film' && !e.bonus ? e.duration ?? 0 : 0), 0);
    out.push({ chapter, all, shown, gap, filmSeconds });
  }
  return out;
}

export type Totals = {
  /** Durée du film actuel (s) : entrées « dans le film », bonus exclus. */
  current: number;
  /** Durée du film visé (s) : dans le film + en attente + à recréer, bonus exclus. */
  planned: number;
  /** Entrées du film visé dont la durée est inconnue (non comptées). */
  unknown: number;
  /** Chapitres sans scène dans le film. */
  gaps: number;
  bonus: number;
};

export function totals(plan: FilmPlan, view: View): Totals {
  const t: Totals = { current: 0, planned: 0, unknown: 0, gaps: 0, bonus: 0 };
  for (const e of plan.entries) {
    if (!inView(e.faction, view)) continue;
    if (e.bonus) { if (e.status === 'film') t.bonus += e.duration ?? 0; continue; }
    if (e.status === 'film') t.current += e.duration ?? 0;
    if (e.status !== 'discarded') {
      if (e.duration === null) t.unknown += 1;
      else t.planned += e.duration;
    }
  }
  t.gaps = timeline(plan, view).filter(c => c.gap !== 'none').length;
  return t;
}

export function formatSeconds(seconds: number): string {
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h} h ${String(m).padStart(2, '0')} min`;
  if (m) return `${m} min ${String(r).padStart(2, '0')} s`;
  return `${r} s`;
}

// --- modifications -------------------------------------------------------------------------------

export function updateEntry(plan: FilmPlan, id: string, patch: Partial<PlanEntry>): FilmPlan {
  return { ...plan, entries: plan.entries.map(e => (e.id === id ? { ...e, ...patch } : e)) };
}

/**
 * Déplace `id` juste avant `beforeId` (ou en fin de chapitre `chapter` si `beforeId` est nul) ;
 * l'entrée prend le chapitre de sa nouvelle place. L'ordre du plan est global : la frise d'une
 * faction en est la sous-suite, comme le film trie ses chapitres communs et de faction ensemble.
 */
export function moveEntry(plan: FilmPlan, id: string, target: { beforeId: string | null; chapter: string }): FilmPlan {
  const entry = plan.entries.find(e => e.id === id);
  if (!entry || target.beforeId === id) return plan;
  if (!plan.chapters.some(c => c.id === target.chapter)) return plan;
  const rest = plan.entries.filter(e => e.id !== id);
  const moved = { ...entry, chapter: target.chapter };
  let index: number;
  if (target.beforeId !== null) {
    index = rest.findIndex(e => e.id === target.beforeId);
    if (index < 0) return plan;
  } else {
    // après la dernière entrée du chapitre, sinon après celles des chapitres qui le précèdent
    const order = new Map(plan.chapters.map((c, i) => [c.id, i]));
    const rank = order.get(target.chapter) ?? 0;
    index = 0;
    rest.forEach((e, i) => { if ((order.get(e.chapter) ?? 0) <= rank) index = i + 1; });
  }
  return { ...plan, entries: [...rest.slice(0, index), moved, ...rest.slice(index)] };
}

/**
 * Flèches : échange l'entrée avec sa voisine visible (`siblings`, entrées affichées du chapitre).
 * Renvoie le plan inchangé en bout de chapitre.
 */
export function stepEntry(plan: FilmPlan, id: string, siblings: readonly PlanEntry[], step: -1 | 1): FilmPlan {
  const i = siblings.findIndex(e => e.id === id);
  const j = i + step;
  if (i < 0 || j < 0 || j >= siblings.length) return plan;
  const entry = siblings[i];
  if (step < 0) return moveEntry(plan, id, { beforeId: siblings[j].id, chapter: entry.chapter });
  const after = siblings[j + 1];
  if (after) return moveEntry(plan, id, { beforeId: after.id, chapter: entry.chapter });
  // la voisine est la dernière affichée : se placer juste après elle
  const rest = plan.entries.filter(e => e.id !== id);
  const k = rest.findIndex(e => e.id === siblings[j].id);
  return { ...plan, entries: [...rest.slice(0, k + 1), entry, ...rest.slice(k + 1)] };
}

export function slug(text: string): string {
  return fold(text).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'scene';
}

/** Ajoute une entrée libre (scène à créer) en fin de chapitre. */
export function addFreeEntry(plan: FilmPlan, chapterId: string, draft: { title: string; duration: number | null; note: string; faction?: PlanFaction }): FilmPlan {
  const chapter = plan.chapters.find(c => c.id === chapterId);
  if (!chapter || !draft.title.trim()) return plan;
  const ids = new Set(plan.entries.map(e => e.id));
  const base = `free-${slug(draft.title)}`;
  let id = base;
  for (let n = 2; ids.has(id); n++) id = `${base}-${n}`;
  const entry: PlanEntry = {
    id, title: draft.title.trim(), chapter: chapterId, faction: draft.faction ?? chapter.faction,
    zone: '', version: chapter.version, kind: 'free', duration: draft.duration, durationEstimated: draft.duration !== null,
    status: 'todo', priority: 'medium', siteChapter: null, ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
  };
  return moveEntry({ ...plan, entries: [...plan.entries, entry] }, id, { beforeId: null, chapter: chapterId });
}

export function removeEntry(plan: FilmPlan, id: string): FilmPlan {
  return { ...plan, entries: plan.entries.filter(e => e.id !== id) };
}

/** Lien vers le chapitre de `/cinematics` (film de la vue, ou de la Ligue pour un chapitre commun). */
export function siteLink(entry: PlanEntry, view: View): string | null {
  if (!entry.siteChapter) return null;
  const faction = entry.faction === 'common' ? (view === 'empire' ? 'empire' : 'league') : entry.faction;
  return `/cinematics?faction=${faction}&chapter=${encodeURIComponent(entry.siteChapter)}`;
}
