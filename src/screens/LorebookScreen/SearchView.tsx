import { useMemo, useState } from 'react';
import { Link } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import type { MessageKey } from '@/lib/i18n/messages';
import { loadDir, loadShard, type LoreMeta } from './lorebook.data';
import { FLAG_COMMUNITY, lorePath, queryTokens, searchIndex, shardKey, type ContentLang, type DirRow, type Shard } from './lorebook.logic';
import { useAsync } from './useAsync';
import s from './LorebookScreen.module.css';

export const PAGE_SIZE = 30;

/** Résultats de recherche : fragments d'index des mots saisis, puis blocs du répertoire des entrées trouvées. */
export async function runSearch(q: string, lang: ContentLang, meta: LoreMeta, limit = PAGE_SIZE): Promise<{ total: number; rows: DirRow[] }> {
  const tokens = queryTokens(q, new Set(meta.stopwords), meta.token_min);
  if (!tokens.length) return { total: 0, rows: [] };
  const keys = [...new Set(tokens.map(shardKey))];
  const shards: Record<string, Shard | undefined> = {};
  await Promise.all(keys.map(async k => { shards[k] = await loadShard(lang, k); }));
  const all = searchIndex(tokens, shards);
  const hits = all.slice(0, limit);
  const total = all.length;
  const blocks = [...new Set(hits.map(h => Math.floor(h.gid / meta.dir_block)))];
  const dirs = new Map<number, DirRow[]>();
  await Promise.all(blocks.map(async b => { dirs.set(b, await loadDir(lang, b)); }));
  const rows = hits.map(h => dirs.get(Math.floor(h.gid / meta.dir_block))?.[h.gid % meta.dir_block]).filter((r): r is DirRow => !!r);
  return { total, rows };
}

export function SearchView({ q, lang, meta }: { q: string; lang: ContentLang; meta: LoreMeta }) {
  const { t } = useI18n();
  const tokens = useMemo(() => queryTokens(q, new Set(meta.stopwords), meta.token_min), [q, meta]);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const result = useAsync(() => (tokens.length ? runSearch(q, lang, meta, limit) : undefined), [q, lang, meta, limit]);
  if (!tokens.length) return <div className={s.searchPane}><p className={s.empty}>{t('lore.searchHint')}</p></div>;
  const data = result.data;
  return (
    <div className={s.searchPane} data-testid="lore-search" lang={lang}>
      {result.loading && !data && <p className={s.empty}>{t('lore.loading')}</p>}
      {data && (
        <>
          <h2 className={s.searchTitle}>
            {data.total ? t('lore.results', { count: data.total, q }) : t('lore.noResults', { q })}

          </h2>
          <ul className={s.results}>
            {data.rows.map(([section, id, title, flags]) => (
              <li key={`${section}/${id}`}>
                <Link to={lorePath({ view: 'entry', section, id })}>
                  <span className={s.resultSection}>{t(`lore.section.${section}` as MessageKey)}</span>
                  <span className={s.resultTitle}>{title}</span>
                  {flags & FLAG_COMMUNITY ? <span className={`${s.badge} ${s.badgeCommunity}`}>{t('lore.badge.community')}</span> : null}
                </Link>
              </li>
            ))}
          </ul>
          {data.total > data.rows.length && (
            <button type="button" className={s.more} onClick={() => setLimit(l => l + PAGE_SIZE)}>
              {t('lore.showMore')} <span className={s.count}>({data.rows.length} / {data.total})</span>
            </button>
          )}
        </>
      )}
    </div>
  );
}
