import { useMemo, useState } from 'react';
import type { Medal, MedalFilter, MedalsDataset } from '@/data/medals.types';
import { filterMedals, medalsOf, searchMedals } from '@/data/medals.logic';

export type Selection = { categoryIndex: number; subCategoryIndex: number };

export function firstNonEmpty(ds: MedalsDataset): Selection {
  for (let c = 0; c < ds.categories.length; c++)
    for (let s = 0; s < ds.categories[c].subCategories.length; s++)
      if (medalsOf(ds, c, s).length) return { categoryIndex: c, subCategoryIndex: s };
  return { categoryIndex: 0, subCategoryIndex: 0 };
}

export function titleFor(ds: MedalsDataset, sel: Selection): string {
  return ds.categories[sel.categoryIndex]?.subCategories[sel.subCategoryIndex]?.name ?? '';
}

export function useMedalsState(ds: MedalsDataset, initialQuery = '') {
  const [selected, setSelected] = useState<Selection>(() => firstNonEmpty(ds));
  const [openCategory, setOpenCategory] = useState<number | null>(selected.categoryIndex);
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState<MedalFilter>('all');

  const select = (categoryIndex: number, subCategoryIndex: number) => { setSelected({ categoryIndex, subCategoryIndex }); setQuery(''); };
  const toggleCategory = (c: number) => setOpenCategory(prev => (prev === c ? null : c));

  const { visible, title } = useMemo(() => {
    if (query.trim()) return { visible: filterMedals(searchMedals(ds, query), filter), title: 'Résultats de la recherche' };
    const list = medalsOf(ds, selected.categoryIndex, selected.subCategoryIndex);
    return { visible: filterMedals(list, filter), title: titleFor(ds, selected) };
  }, [ds, query, filter, selected]);

  return { selected, select, openCategory, toggleCategory, query, setQuery, filter, setFilter, visible: visible as Medal[], title };
}
export type MedalsState = ReturnType<typeof useMedalsState>;
