import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import { firstNonEmpty, initialCategory, titleFor, useMedalsState } from './useMedalsState';

const EMPTY_DATASET: MedalsDataset = { categories: [], medals: [], totalScore: 0 };
const ds = parseDataset(mock);
const ASTRAL = ds.categories.findIndex(c => c.name === 'Astral');

describe('firstNonEmpty', () => {
  it('sélectionne Personnage / Équipement pour le mock', () => {
    const sel = firstNonEmpty(ds);
    expect(ds.categories[sel.categoryIndex].name).toBe('Personnage');
    expect(ds.categories[sel.categoryIndex].subCategories[sel.subCategoryIndex].name).toBe('Équipement');
  });

  it('renvoie {0, 0} pour un dataset vide, sans planter', () => {
    expect(firstNonEmpty(EMPTY_DATASET)).toEqual({ categoryIndex: 0, subCategoryIndex: 0 });
  });
});

describe('initialCategory', () => {
  it('ouvre Astral, la catégorie de la capture de référence', () => {
    expect(initialCategory(ds)).toBe(ASTRAL);
  });

  it('retombe sur la première catégorie non vide si Astral n’existe pas', () => {
    const sansAstral: MedalsDataset = { ...ds, categories: ds.categories.filter(c => c.name !== 'Astral') };
    expect(initialCategory(sansAstral)).toBe(firstNonEmpty(sansAstral).categoryIndex);
  });

  it('renvoie null pour un dataset vide', () => {
    expect(initialCategory(EMPTY_DATASET)).toBeNull();
  });
});

describe('titleFor', () => {
  it('renvoie le nom de la sous-catégorie sélectionnée', () => {
    expect(titleFor(ds, { categoryIndex: ASTRAL, subCategoryIndex: 0 })).toBe('Astral ouvert');
  });

  it('renvoie une chaîne vide sans sélection', () => {
    expect(titleFor(ds, null)).toBe('');
  });

  it('renvoie une chaîne vide pour un dataset vide plutôt que de planter', () => {
    expect(titleFor(EMPTY_DATASET, { categoryIndex: 0, subCategoryIndex: 0 })).toBe('');
  });
});

describe('useMedalsState', () => {
  it('démarre sur Astral déplié et « Astral ouvert » sélectionné, comme refs/astral.png', () => {
    const { result } = renderHook(() => useMedalsState(ds));
    expect(result.current.openCategory).toBe(ASTRAL);
    expect(result.current.selected).toEqual({ categoryIndex: ASTRAL, subCategoryIndex: 0 });
    expect(result.current.title).toBe('Astral ouvert');
  });

  it('déplie une catégorie et sélectionne sa première sous-catégorie, en repliant l’autre', () => {
    const { result } = renderHook(() => useMedalsState(ds));
    act(() => result.current.toggleCategory(1));
    expect(result.current.openCategory).toBe(1);
    expect(result.current.selected).toEqual({ categoryIndex: 1, subCategoryIndex: 0 });
  });

  it('replie la catégorie ouverte et vide la sélection', () => {
    const { result } = renderHook(() => useMedalsState(ds));
    act(() => result.current.toggleCategory(1));
    act(() => result.current.toggleCategory(1));
    expect(result.current.openCategory).toBeNull();
    expect(result.current.selected).toBeNull();
    expect(result.current.title).toBe('');
    expect(result.current.visible).toEqual([]);
  });

  it('mémorise le suivi d’un succès et le reflète dans la liste visible', () => {
    const { result } = renderHook(() => useMedalsState(ds));
    const id = result.current.visible[0].id;
    act(() => result.current.setTracked(id, false));
    expect(result.current.visible.find(m => m.id === id)?.tracked).toBe(false);
    act(() => result.current.setTracked(id, true));
    expect(result.current.visible.find(m => m.id === id)?.tracked).toBe(true);
    act(() => result.current.setTracked(id, false));
    expect(result.current.visible.find(m => m.id === id)?.tracked).toBe(false);
  });

  it('sélectionner une sous-catégorie efface la recherche en cours', () => {
    const { result } = renderHook(() => useMedalsState(ds, 'étoiles'));
    expect(result.current.query).toBe('étoiles');
    act(() => result.current.select(ASTRAL, 1));
    expect(result.current.query).toBe('');
    expect(result.current.selected).toEqual({ categoryIndex: ASTRAL, subCategoryIndex: 1 });
  });
});
