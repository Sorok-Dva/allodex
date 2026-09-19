import { useRef } from 'react';
import { T, sprite, tex } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import { subCategoryCounts } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import { GameScrollbar } from '@/components/game/GameScrollbar';
import type { MedalsState } from './useMedalsState';
import s from './MedalsNavigation.module.css';

/** Pas entre deux lignes de la sous-liste (`refs/astral.png` : textes à y 453 et 476). */
const SUB_ROW = 23;
/** Marges verticales du parchemin autour des lignes (12 px en haut, 15 px en bas). */
const SUB_PADDING = 27;
/**
 * « Progression » est une vue, pas une catégorie dépliable : elle n'a pas de médaillon
 * +/− et le clic reste sans effet (spec § 7.2). C'est toujours la première entrée de
 * l'ordre du jeu.
 */
const PROGRESSION_INDEX = 0;

export function MedalsNavigation({ ds, state }: { ds: MedalsDataset; state: MedalsState }) {
  const listRef = useRef<HTMLDivElement>(null);

  return (
    <div className={s.nav}>
      <div className={s.search}>
        <span className={s.searchFrame} style={nineSlice('search-field', [5, 6, 5, 6], { fill: true })} aria-hidden="true" />
        <input
          className={s.searchInput}
          value={state.query}
          onChange={e => state.setQuery(e.target.value)}
          placeholder="Recherche de succès..."
          spellCheck={false}
          aria-label="Recherche de succès"
        />
      </div>

      <div className={s.viewport} ref={listRef}>
        <ul className={s.list}>
          {ds.categories.map((cat, c) => {
            const open = state.openCategory === c;
            const foldable = c !== PROGRESSION_INDEX;
            return (
              <li key={cat.name} className={s.item}>
                <button
                  type="button"
                  className={s.pill}
                  aria-expanded={foldable ? open : undefined}
                  aria-disabled={foldable ? undefined : true}
                  onClick={foldable ? () => state.toggleCategory(c) : undefined}
                >
                  <span
                    className={s.pillSkin}
                    style={{ backgroundImage: `url(${sprite(open ? 'pill-full-open' : 'pill-full')})` }}
                    aria-hidden="true"
                  />
                  <span className={s.pillLabel}>{cat.name}</span>
                  {foldable && (
                    <span
                      className={s.medallion}
                      style={{ backgroundImage: `url(${sprite(open ? 'medallion-minus' : 'medallion-plus')})` }}
                    />
                  )}
                </button>

                {open && (
                  <div className={s.subWrap} style={{ height: cat.subCategories.length * SUB_ROW + SUB_PADDING }}>
                    <span
                      className={s.parchment}
                      style={{ backgroundImage: `url(${tex(`${T.medals}/CategoryContent`)})` }}
                      aria-hidden="true"
                    />
                    <ul className={s.subList}>
                      {cat.subCategories.map((sub, i) => {
                        const { done, total } = subCategoryCounts(ds, c, i);
                        const active = state.selected?.categoryIndex === c && state.selected.subCategoryIndex === i;
                        return (
                          <li key={sub.name}>
                            <button
                              type="button"
                              className={`${s.subRow} ${active ? s.subActive : ''}`}
                              style={{ top: 12 + i * SUB_ROW }}
                              onClick={() => state.select(c, i)}
                            >
                              {sub.name} - {done}/{total}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <GameScrollbar targetRef={listRef} className={s.scrollbar} />
    </div>
  );
}
