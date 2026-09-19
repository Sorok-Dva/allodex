import { useMemo, useState } from 'react';
import type { Medal, MedalFilter, MedalsDataset } from '@/data/medals.types';
import { filterMedals, medalsOf, searchMedals } from '@/data/medals.logic';

export type Selection = { categoryIndex: number; subCategoryIndex: number };

/** Catégorie dépliée au chargement : celle de la capture de référence `refs/astral.png`. */
const INITIAL_CATEGORY = 'Astral';

export function firstNonEmpty(ds: MedalsDataset): Selection {
  for (let c = 0; c < ds.categories.length; c++)
    for (let s = 0; s < ds.categories[c].subCategories.length; s++)
      if (medalsOf(ds, c, s).length) return { categoryIndex: c, subCategoryIndex: s };
  return { categoryIndex: 0, subCategoryIndex: 0 };
}

/**
 * Catégorie ouverte au chargement. Le jeu n'en ouvre aucune, mais la spécification
 * (§ 7.2) demande de partir sur « Astral » pour que l'écran corresponde à la capture.
 */
export function initialCategory(ds: MedalsDataset): number | null {
  if (!ds.categories.length) return null;
  const astral = ds.categories.findIndex(c => c.name === INITIAL_CATEGORY);
  return astral >= 0 ? astral : firstNonEmpty(ds).categoryIndex;
}

export function titleFor(ds: MedalsDataset, sel: Selection | null): string {
  if (!sel) return '';
  return ds.categories[sel.categoryIndex]?.subCategories[sel.subCategoryIndex]?.name ?? '';
}

export function useMedalsState(ds: MedalsDataset, initialQuery = '') {
  const [openCategory, setOpenCategory] = useState<number | null>(() => initialCategory(ds));
  const [selected, setSelected] = useState<Selection | null>(() => {
    const c = initialCategory(ds);
    return c === null ? null : { categoryIndex: c, subCategoryIndex: 0 };
  });
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState<MedalFilter>('all');
  const [tracked, setTrackedMap] = useState<ReadonlyMap<string, boolean>>(() => new Map());

  const select = (categoryIndex: number, subCategoryIndex: number) => {
    setSelected({ categoryIndex, subCategoryIndex });
    setQuery('');
  };

  /** Déplier sélectionne la première sous-catégorie ; replier vide la sélection. */
  const toggleCategory = (c: number) => {
    const closing = openCategory === c;
    setOpenCategory(closing ? null : c);
    setSelected(closing ? null : { categoryIndex: c, subCategoryIndex: 0 });
    setQuery('');
  };

  /** Suivi local d'un succès (case à cocher du jeu), non persisté. */
  const setTracked = (medalId: string, value: boolean) =>
    setTrackedMap(prev => new Map(prev).set(medalId, value));

  const { visible, title } = useMemo(() => {
    const withTracking = (list: Medal[]) =>
      tracked.size === 0 ? list : list.map(m => (tracked.has(m.id) ? { ...m, tracked: tracked.get(m.id) } : m));
    if (query.trim())
      return { visible: withTracking(filterMedals(searchMedals(ds, query), filter)), title: 'Résultats de la recherche' };
    if (!selected) return { visible: [] as Medal[], title: '' };
    const list = medalsOf(ds, selected.categoryIndex, selected.subCategoryIndex);
    return { visible: withTracking(filterMedals(list, filter)), title: titleFor(ds, selected) };
  }, [ds, query, filter, selected, tracked]);

  return { selected, select, openCategory, toggleCategory, query, setQuery, filter, setFilter, tracked, setTracked, visible, title };
}
export type MedalsState = ReturnType<typeof useMedalsState>;
