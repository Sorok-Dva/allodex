import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, navigate } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import type { MessageKey } from '@/lib/i18n/messages';
import { FLAG_COMMUNITY, FLAG_EN_MISSING, listRows, lorePath, visibleRange, type ContentLang, type ListData, type ListGroup, type SectionId } from './lorebook.logic';
import s from './LorebookScreen.module.css';

export const ROW_HEIGHT = 52;

export function groupLabel(g: ListGroup, t: (k: MessageKey) => string): string {
  return g.key ? t(g.key as MessageKey) : g.label ?? g.id;
}

type Props = {
  section: SectionId;
  list: ListData;
  lang: ContentLang;
  selected?: string;
  group?: string;
};

/**
 * Liste virtualisée d'une section : seules les lignes visibles (plus une marge) sont dans le DOM,
 * ce qui garde fluides les 15 000 entrées des personnages. Un filtre par groupe restreint la liste.
 */
export function EntryList({ section, list, lang, selected, group }: Props) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(600);
  const groupIndex = group ? list.groups.findIndex(g => g.id === group) : -1;
  const rows = useMemo(() => listRows(list, g => groupLabel(g, t), groupIndex >= 0 ? groupIndex : undefined), [list, t, groupIndex]);
  const [first, last] = visibleRange(scroll, height, ROW_HEIGHT, rows.length);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => setHeight(el.clientHeight || 600)) : null;
    ro?.observe(el);
    setHeight(el.clientHeight || 600);
    return () => ro?.disconnect();
  }, []);

  // L'entrée ouverte reste visible : on fait défiler la liste jusqu'à elle si besoin.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !selected) return;
    const i = rows.findIndex(r => r.kind === 'entry' && list.rows[r.index][0] === selected);
    if (i < 0) return;
    const top = i * ROW_HEIGHT;
    if (top < el.scrollTop || top + ROW_HEIGHT > el.scrollTop + el.clientHeight) {
      el.scrollTop = Math.max(0, top - el.clientHeight / 3);
      setScroll(el.scrollTop);
    }
  }, [selected, rows, list]);

  const filter = list.groups.length > 1 && (
    <div className={s.groupFilter} role="group" aria-label={t('lore.groupFilter')}>
      <button type="button" aria-pressed={groupIndex < 0} onClick={() => navigate(lorePath({ view: 'section', section }), { replace: true })}>{t('lore.allGroups')}</button>
      {list.groups.filter(g => g.count > 0).slice(0, 40).map(g => (
        <button key={g.id} type="button" aria-pressed={g.id === group}
          onClick={() => navigate(lorePath({ view: 'section', section, group: g.id }), { replace: true })}>
          {groupLabel(g, t)} <span className={s.count}>{g.count}</span>
        </button>
      ))}
    </div>
  );

  return (
    <div className={s.listPane}>
      {filter}
      <div className={s.listViewport} ref={ref} onScroll={e => setScroll(e.currentTarget.scrollTop)} data-testid="lore-list" lang={lang}>
        <div style={{ height: rows.length * ROW_HEIGHT, position: 'relative' }}>
          {rows.slice(first, last).map((row, k) => {
            const top = (first + k) * ROW_HEIGHT;
            if (row.kind === 'group') {
              return <div key={`g${row.group}`} className={s.groupRow} style={{ top, height: ROW_HEIGHT }}>{row.label} <span className={s.count}>{row.count}</span></div>;
            }
            const [id, , , flags, title, subtitle] = list.rows[row.index];
            return (
              <Link key={id} to={lorePath({ view: 'entry', section, id })} className={`${s.row} ${id === selected ? s.rowSelected : ''}`} style={{ top, height: ROW_HEIGHT }}>
                <span className={s.rowTitle}>{title}</span>
                <span className={s.rowSub}>
                  {flags & FLAG_COMMUNITY ? <span className={`${s.badge} ${s.badgeCommunity}`}>{t('lore.badge.community')}</span> : null}
                  {lang === 'en' && flags & FLAG_EN_MISSING ? <span className={`${s.badge} ${s.badgeMissing}`}>{t('lore.badge.untranslatedShort')}</span> : null}
                  {subtitle}
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
