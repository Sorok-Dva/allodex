import { T, tex } from '@/lib/assets';
import { subCategoryCounts } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import type { MedalsState } from './useMedalsState';
import s from './MedalsNavigation.module.css';

export function MedalsNavigation({ ds, state }: { ds: MedalsDataset; state: MedalsState }) {
  return (
    <aside className={s.nav} style={{ backgroundImage: `url(${tex(`${T.medals}/FrameNavigation`)})` }}>
      <label className={s.search} style={{ backgroundImage: `url(${tex(`${T.login}/EditlineFrame`)})` }}>
        <input value={state.query} onChange={e => state.setQuery(e.target.value)} placeholder="Recherche de succès..." spellCheck={false} />
      </label>

      <ul className={s.categories}>
        {ds.categories.map((cat, c) => {
          const open = state.openCategory === c;
          return (
            <li key={cat.name} className={s.category}>
              <button type="button" className={`${s.catButton} ${open ? s.catOpen : ''}`} onClick={() => state.toggleCategory(c)}>
                <span>{cat.name}</span>
                <span className={s.toggle}>{open ? '−' : '+'}</span>
              </button>
              {open && (
                <ul className={s.subList} style={{ backgroundImage: `url(${tex(`${T.medals}/CategoryContent`)})` }}>
                  {cat.subCategories.map((sub, i) => {
                    const { done, total } = subCategoryCounts(ds, c, i);
                    const active = !state.query && state.selected.categoryIndex === c && state.selected.subCategoryIndex === i;
                    return (
                      <li key={sub.name}>
                        <button type="button" className={`${s.subButton} ${active ? s.subActive : ''}`} onClick={() => state.select(c, i)}>
                          {sub.name} - {done}/{total}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
