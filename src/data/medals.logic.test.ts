import { describe, it, expect } from 'vitest';
import type { Medal, MedalsDataset } from './medals.types';
import {
  parseDataset, isComplete, currentRankOf, frameForScore,
  subCategoryCounts, filterMedals, searchMedals, medalsOf,
} from './medals.logic';
import mock from './medals.mock.json';

const rank = (score: number, completeProgress = 1) => ({ completeProgress, name: 'r', description: 'd', score });

const medal = (over: Partial<Medal>): Medal => ({
  id: 'x', name: 'Nom', description: 'Desc', icon: 'i',
  categoryIndex: 0, subCategoryIndex: 0, ranks: [rank(10)], currentRank: 0, ...over,
});

const ds: MedalsDataset = {
  categories: [{ name: 'Personnage', subCategories: [{ name: 'Équipement' }, { name: 'Divers' }] }],
  totalScore: 0,
  medals: [
    medal({ id: 'a', name: 'Paré pour l\'aventure ! (Réveil)', ranks: [rank(10, 21500)], currentRank: 1, finishDate: '2019-01-28' }),
    medal({ id: 'b', name: 'Dragon des temps nouveaux', description: 'Équipez un ensemble complet', ranks: [rank(100)], currentRank: 0 }),
    medal({ id: 'c', name: 'Glaneur', subCategoryIndex: 1, ranks: [rank(10), rank(30)], currentRank: 1 }),
  ],
};

describe('isComplete / currentRankOf', () => {
  it('est terminé quand currentRank atteint le nombre de paliers', () => {
    expect(isComplete(ds.medals[0])).toBe(true);
    expect(isComplete(ds.medals[2])).toBe(false);
  });
  it('renvoie le palier en cours, ou le dernier si terminé', () => {
    expect(currentRankOf(ds.medals[2]).score).toBe(30);
    expect(currentRankOf(ds.medals[0]).score).toBe(10);
  });
});

describe('frameForScore', () => {
  it('choisit le cadre par seuil', () => {
    expect(frameForScore(10)).toBe(30);
    expect(frameForScore(30)).toBe(30);
    expect(frameForScore(75)).toBe(50);
    expect(frameForScore(100)).toBe(100);
    expect(frameForScore(1000)).toBe(500);
  });
});

describe('subCategoryCounts / medalsOf', () => {
  it('compte terminés/total par sous-catégorie', () => {
    expect(subCategoryCounts(ds, 0, 0)).toEqual({ done: 1, total: 2 });
    expect(subCategoryCounts(ds, 0, 1)).toEqual({ done: 0, total: 1 });
    expect(medalsOf(ds, 0, 1).map(m => m.id)).toEqual(['c']);
  });
});

describe('filterMedals', () => {
  it('filtre Tout / Terminés / En cours', () => {
    expect(filterMedals(ds.medals, 'all')).toHaveLength(3);
    expect(filterMedals(ds.medals, 'completed').map(m => m.id)).toEqual(['a']);
    expect(filterMedals(ds.medals, 'inProgress').map(m => m.id)).toEqual(['b', 'c']);
  });
});

describe('searchMedals', () => {
  it('cherche sans casse ni accents dans nom et description', () => {
    expect(searchMedals(ds, 'PARE').map(m => m.id)).toEqual(['a']);
    expect(searchMedals(ds, 'equipez').map(m => m.id)).toEqual(['b']);
    expect(searchMedals(ds, '')).toHaveLength(3);
  });
});

describe('parseDataset', () => {
  it('accepte un dataset valide et rejette un succès sans palier', () => {
    expect(parseDataset(ds)).toBe(ds);
    expect(() => parseDataset({ ...ds, medals: [medal({ ranks: [] })] })).toThrow(/ranks/);
    expect(() => parseDataset({ ...ds, medals: [medal({ categoryIndex: 7 })] })).toThrow(/categoryIndex/);
  });

  it('le mock est un dataset valide', () => {
    const parsed = parseDataset(mock);
    expect(parsed.medals.length).toBeGreaterThanOrEqual(16);
    expect(subCategoryCounts(parsed, 1, 0)).toEqual({ done: 4, total: 4 });
  });

  it('rejette un currentRank manquant ou non entier', () => {
    expect(() => parseDataset({ ...ds, medals: [medal({ currentRank: undefined as unknown as number })] })).toThrow(/currentRank/);
    expect(() => parseDataset({ ...ds, medals: [medal({ currentRank: 0.5 })] })).toThrow(/currentRank/);
  });

  it('rejette un palier avec completeProgress à 0', () => {
    expect(() => parseDataset({ ...ds, medals: [medal({ ranks: [rank(10, 0)] })] })).toThrow(/ranks\[0\]/);
  });

  it('rejette les id dupliqués', () => {
    expect(() => parseDataset({ ...ds, medals: [medal({ id: 'dup' }), medal({ id: 'dup' })] })).toThrow(/id dupliqué/);
  });
});
