import type { Medal, MedalFilter, MedalRank, MedalsDataset } from './medals.types';

export function isComplete(m: Medal): boolean {
  return m.currentRank >= m.ranks.length;
}

export function currentRankOf(m: Medal): MedalRank {
  return m.ranks[Math.min(m.currentRank, m.ranks.length - 1)];
}

/**
 * Palier de l'écu, relevé sur `refs/astral.png` : « Connecté avec les étoiles » (20 pts)
 * et « Parfait ! » (10 pts) portent le cadre nu `MedalFrame*` avec le chiffre romain « I »,
 * « Propriétaire » (30 pts) le cadre à pointes `MedalFrame*30` avec « II ». Le seuil du
 * palier est donc le score : < 30 → I, 30 → II, 50 → III, 100 → IV, 500 → V.
 */
const FRAME_TIERS = [30, 50, 100, 500] as const;
export type MedalTier = 1 | 2 | 3 | 4 | 5;

export function medalTier(score: number): MedalTier {
  let tier = 1;
  for (const threshold of FRAME_TIERS) if (score >= threshold) tier += 1;
  return tier as MedalTier;
}

/** Suffixe de texture : `''` pour le palier I (`MedalFrame`), sinon `30`/`50`/`100`/`500`. */
export function frameSuffix(score: number): '' | '30' | '50' | '100' | '500' {
  const tier = medalTier(score);
  return tier === 1 ? '' : (String(FRAME_TIERS[tier - 2]) as '30' | '50' | '100' | '500');
}

export function medalsOf(ds: MedalsDataset, categoryIndex: number, subCategoryIndex: number): Medal[] {
  return ds.medals.filter(m => m.categoryIndex === categoryIndex && m.subCategoryIndex === subCategoryIndex);
}

export function subCategoryCounts(ds: MedalsDataset, categoryIndex: number, subCategoryIndex: number) {
  const list = medalsOf(ds, categoryIndex, subCategoryIndex);
  return { done: list.filter(isComplete).length, total: list.length };
}

export function filterMedals(medals: Medal[], filter: MedalFilter): Medal[] {
  if (filter === 'completed') return medals.filter(isComplete);
  if (filter === 'inProgress') return medals.filter(m => !isComplete(m));
  return medals;
}

export const FILTER_LABELS: Record<MedalFilter, string> = {
  all: 'Tout',
  completed: 'Terminé',
  inProgress: 'Pas terminé',
};

export function normalize(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

export function searchMedals(ds: MedalsDataset, query: string): Medal[] {
  const q = normalize(query.trim());
  if (!q) return ds.medals;
  return ds.medals.filter(m => normalize(m.name).includes(q) || normalize(m.description).includes(q));
}

function fail(path: string, msg: string): never {
  throw new Error(`Dataset invalide (${path}) : ${msg}`);
}

export function parseDataset(raw: unknown): MedalsDataset {
  const ds = raw as MedalsDataset;
  if (!ds || !Array.isArray(ds.categories) || !Array.isArray(ds.medals)) fail('root', 'categories/medals manquants');
  if (typeof ds.totalScore !== 'number') fail('totalScore', 'nombre attendu');
  const seenIds = new Set<string>();
  ds.medals.forEach((m, i) => {
    const p = `medals[${i}]`;
    if (!m.id || !m.name) fail(p, 'id/name manquants');
    if (seenIds.has(m.id)) fail(`${p}.id`, 'id dupliqué');
    seenIds.add(m.id);
    if (!Array.isArray(m.ranks) || m.ranks.length === 0) fail(`${p}.ranks`, 'au moins un palier requis');
    m.ranks.forEach((r, j) => {
      const valid = typeof r.completeProgress === 'number' && r.completeProgress >= 1
        && typeof r.score === 'number' && typeof r.name === 'string' && typeof r.description === 'string';
      if (!valid) fail(`${p}.ranks[${j}]`, 'palier invalide');
    });
    const cat = ds.categories[m.categoryIndex];
    if (!cat) fail(`${p}.categoryIndex`, `catégorie ${m.categoryIndex} inexistante`);
    if (!cat.subCategories[m.subCategoryIndex]) fail(`${p}.subCategoryIndex`, `sous-catégorie ${m.subCategoryIndex} inexistante`);
    if (typeof m.currentRank !== 'number' || !Number.isInteger(m.currentRank)) fail(`${p}.currentRank`, 'nombre entier attendu');
    if (m.currentRank < 0 || m.currentRank > m.ranks.length) fail(`${p}.currentRank`, 'hors bornes');
    m.medalCollection?.forEach((c, k) => {
      if (!Number.isInteger(c.rank) || c.rank < 1) fail(`${p}.medalCollection[${k}].rank`, 'entier >= 1 attendu');
    });
  });
  return ds;
}
