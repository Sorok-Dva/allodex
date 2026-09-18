import { describe, it, expect } from 'vitest';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import { firstNonEmpty } from './useMedalsState';

describe('firstNonEmpty', () => {
  it('sélectionne Personnage / Équipement pour le mock', () => {
    const ds = parseDataset(mock);
    const sel = firstNonEmpty(ds);
    expect(ds.categories[sel.categoryIndex].name).toBe('Personnage');
    expect(ds.categories[sel.categoryIndex].subCategories[sel.subCategoryIndex].name).toBe('Équipement');
  });
});
