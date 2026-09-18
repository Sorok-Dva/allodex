import { describe, it, expect } from 'vitest';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import { firstNonEmpty, titleFor } from './useMedalsState';

const EMPTY_DATASET: MedalsDataset = { categories: [], medals: [], totalScore: 0 };

describe('firstNonEmpty', () => {
  it('sélectionne Personnage / Équipement pour le mock', () => {
    const ds = parseDataset(mock);
    const sel = firstNonEmpty(ds);
    expect(ds.categories[sel.categoryIndex].name).toBe('Personnage');
    expect(ds.categories[sel.categoryIndex].subCategories[sel.subCategoryIndex].name).toBe('Équipement');
  });

  it('renvoie {0, 0} pour un dataset vide, sans planter', () => {
    expect(firstNonEmpty(EMPTY_DATASET)).toEqual({ categoryIndex: 0, subCategoryIndex: 0 });
  });
});

describe('titleFor', () => {
  it('renvoie le nom de la sous-catégorie sélectionnée', () => {
    const ds = parseDataset(mock);
    const sel = firstNonEmpty(ds);
    expect(titleFor(ds, sel)).toBe('Équipement');
  });

  it('renvoie une chaîne vide pour un dataset vide plutôt que de planter', () => {
    expect(titleFor(EMPTY_DATASET, { categoryIndex: 0, subCategoryIndex: 0 })).toBe('');
  });
});
