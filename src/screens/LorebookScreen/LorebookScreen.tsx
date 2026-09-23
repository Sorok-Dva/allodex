import { useCallback, useEffect, useRef, useState } from 'react';
import { T, tex } from '@/lib/assets';
import { Link, navigate, useRoute } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import type { MessageKey } from '@/lib/i18n/messages';
import { LanguageSwitcher } from '@/components/controls/LanguageSwitcher';
import { loadList, loadMeta, type LoreMeta } from './lorebook.data';
import { CONTENT_LANGS, SECTIONS, isHidden, lorePath, parseLoreRoute, type ContentLang, type LoreRoute, type SectionId } from './lorebook.logic';
import { EntryList } from './EntryList';
import { EntryView } from './EntryView';
import { SearchView } from './SearchView';
import { useAsync } from './useAsync';
import s from './LorebookScreen.module.css';

export const CONTENT_LANG_KEY = 'allodex:loreLang';
const isContentLang = (v: string | null | undefined): v is ContentLang => !!v && (CONTENT_LANGS as readonly string[]).includes(v);

/** Langue du contenu : `?text=` (partage), sinon le choix mémorisé, sinon l'anglais (langue cible du Lorebook). */
export function initialContentLang(search: string, storage: Storage | null): ContentLang {
  const fromUrl = new URLSearchParams(search).get('text');
  if (isContentLang(fromUrl)) return fromUrl;
  try {
    const stored = storage?.getItem(CONTENT_LANG_KEY);
    if (isContentLang(stored)) return stored;
  } catch { /* stockage indisponible */ }
  return 'en';
}

const FRAME = 'Interface/Ingame/QuestLog/textures';

function SectionHome({ meta }: { meta: LoreMeta }) {
  const { t } = useI18n();
  return (
    <div className={s.home} data-testid="lore-home">
      <p className={s.intro}>{t('lore.intro')}</p>
      <ul className={s.cards}>
        {SECTIONS.map(section => (
          <li key={section}>
            <Link to={lorePath({ view: 'section', section })} className={s.card}>
              <span className={s.cardTitle}>{t(`lore.section.${section}` as MessageKey)}</span>
              <span className={s.cardHint}>{t(`lore.sectionHint.${section}` as MessageKey)}</span>
              <span className={s.count}>{t('lore.entries', { count: meta.sections[section]?.count ?? 0 })}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Section cachée : pas de liste, une seule page de lecture (entrée atteinte par recherche ou lien). */
function HiddenPane({ route, lang, meta }: { route: Extract<LoreRoute, { section: SectionId }>; lang: ContentLang; meta: LoreMeta }) {
  const { t } = useI18n();
  return (
    <div className={`${s.book} ${s.bookSingle}`}>
      <div className={s.pageRight} style={{ borderImageSource: `url(${tex(`${FRAME}/MainFrameRight`)})` }}>
        {route.view === 'entry'
          ? <EntryView key={`${route.section}/${route.id}`} section={route.section} id={route.id} lang={lang} meta={meta} />
          : <div className={s.entry}><p className={s.empty}>{t('lore.hiddenSection')}</p></div>}
      </div>
    </div>
  );
}

function SectionPane({ route, lang, meta }: { route: Extract<LoreRoute, { section: SectionId }>; lang: ContentLang; meta: LoreMeta }) {
  const { t } = useI18n();
  const list = useAsync(() => (isHidden(route.section) ? undefined : loadList(lang, route.section)), [lang, route.section]);
  if (isHidden(route.section)) return <HiddenPane route={route} lang={lang} meta={meta} />;
  if (list.error) return <p className={s.empty}>{t('lore.error')}</p>;
  if (!list.data) return <p className={s.empty}>{t('lore.loading')}</p>;
  const entry = route.view === 'entry';
  return (
    <div className={`${s.book} ${entry ? s.bookEntry : s.bookList}`}>
      <div className={s.pageLeft} style={{ borderImageSource: `url(${tex(`${FRAME}/MainFrameLeft`)})` }}>
        <EntryList section={route.section} list={list.data} lang={lang} selected={entry ? route.id : undefined} group={route.view === 'section' ? route.group : undefined} />
      </div>
      <div className={s.pageRight} style={{ borderImageSource: `url(${tex(`${FRAME}/MainFrameRight`)})` }}>
        {entry
          ? <EntryView key={`${route.section}/${route.id}`} section={route.section} id={route.id} list={list.data} lang={lang} meta={meta} />
          : (
            <div className={s.entry}>
              <h2 className={s.entryTitle}>{t(`lore.section.${route.section}` as MessageKey)}</h2>
              <p className={s.entrySub}>{t(`lore.sectionHint.${route.section}` as MessageKey)}</p>
              <p className={s.count}>{t('lore.entries', { count: list.data.rows.length })}</p>
            </div>
          )}
      </div>
    </div>
  );
}

export function LorebookScreen({ storage = typeof window !== 'undefined' ? window.localStorage : null }: { storage?: Storage | null } = {}) {
  const { t } = useI18n();
  const { path, query } = useRoute();
  const route = parseLoreRoute(path, query);
  const [lang, setLangState] = useState<ContentLang>(() => initialContentLang(window.location.search, storage));
  const meta = useAsync(() => loadMeta(), []);
  const [q, setQ] = useState(route.view === 'search' ? route.q : '');
  const debounce = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => { if (route.view === 'search') setQ(route.q); }, [route.view, route.view === 'search' ? route.q : '']);

  const setLang = useCallback((next: ContentLang) => {
    setLangState(next);
    try { storage?.setItem(CONTENT_LANG_KEY, next); } catch { /* stockage indisponible */ }
    const url = new URL(window.location.href);
    if (url.searchParams.has('text')) { url.searchParams.set('text', next); window.history.replaceState(window.history.state, '', url); }
  }, [storage]);

  const onSearch = (value: string) => {
    setQ(value);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      if (value.trim()) navigate(lorePath({ view: 'search', q: value.trim() }), { replace: route.view === 'search' });
      else if (route.view === 'search') navigate(lorePath({ view: 'home' }), { replace: true });
    }, 250);
  };

  const active = route.view === 'section' || route.view === 'entry' ? route.section : null;

  return (
    <div className={s.screen} style={{ backgroundImage: `url(${tex(`${T.main2}/Background_14_0_Temp`)})` }}>
      <div className={s.shade} />
      <header className={s.header}>
        <Link to="/" className={s.backHome}>‹ <span>{t('lore.back')}</span></Link>
        <Link to={lorePath({ view: 'home' })} className={s.plate}>
          <span className={s.plateSkin} aria-hidden="true" style={{ borderImageSource: `url(${tex('Interface/Ingame/Contextructor/WindowHeader/TiledHeader')})` }} />
          <h1 className={s.title}>{t('lore.title')}</h1>
        </Link>
        <div className={s.tools}>
          <input type="search" className={s.search} value={q} onChange={e => onSearch(e.target.value)} placeholder={t('lore.searchPlaceholder')} aria-label={t('lore.search')} />
          <div className={s.langs} role="group" aria-label={t('lore.contentLang')} title={t('lore.contentLang')}>
            <span className={s.langsLabel} aria-hidden="true">{t('lore.textsShort')}</span>
            {CONTENT_LANGS.map(l => <button key={l} type="button" aria-pressed={l === lang} onClick={() => setLang(l)} lang={l}>{l.toUpperCase()}</button>)}
          </div>
          <LanguageSwitcher className={s.uiLang} />
        </div>
      </header>
      <nav className={s.tabs} aria-label={t('lore.sections')}>
        {SECTIONS.map(section => (
          <Link key={section} to={lorePath({ view: 'section', section })} className={`${s.tab} ${active === section ? s.tabActive : ''}`}>
            {t(`lore.section.${section}` as MessageKey)}
          </Link>
        ))}
      </nav>
      <main className={s.main}>
        {meta.error ? <p className={s.empty}>{t('lore.error')}</p>
          : !meta.data ? <p className={s.empty}>{t('lore.loading')}</p>
          : route.view === 'home' ? <SectionHome meta={meta.data} />
          : route.view === 'search' ? <SearchView key={`${lang}:${route.q}`} q={route.q} lang={lang} meta={meta.data} />
          : <SectionPane route={route} lang={lang} meta={meta.data} />}
      </main>
      <footer className={s.footer}>
        <p>{t('lore.credit')} {meta.data ? <a href={meta.data.credit.url} target="_blank" rel="noopener noreferrer">{meta.data.credit.line}</a> : null}</p>
        <p>{t('lore.footer')} {t('home.disclaimer')}</p>
      </footer>
    </div>
  );
}
