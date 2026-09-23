import { useEffect, useMemo } from 'react';
import { Link } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import { MESSAGES, type MessageKey } from '@/lib/i18n/messages';
import { loadChunk, loadHiddenIndex, loadNames, type LoreMeta } from './lorebook.data';
import {
  FLAG_COMMUNITY, chunkForId, isHidden, lorePath, neededFallbacks, refPath, resolveBody,
  type Body, type ContentLang, type Links, type ListData, type ResolvedText, type SectionId,
} from './lorebook.logic';
import { loreEntryTitle } from '@/seo/meta';
import { RichText } from './RichText';
import { useAsync } from './useAsync';
import s from './LorebookScreen.module.css';

const hasKey = (k: string): k is MessageKey => k in MESSAGES.fr;
const LINK_ORDER = ['secrets', 'region', 'place', 'places', 'characters', 'quests'];

type Props = { section: SectionId; id: string; list?: ListData; lang: ContentLang; meta: LoreMeta };

function Badges({ text, lang }: { text: ResolvedText; lang: ContentLang }) {
  const { t } = useI18n();
  return (
    <>
      {text.from && <span className={`${s.badge} ${s.badgeMissing}`} lang={text.from}>{t('lore.badge.untranslated', { lang: t(`lore.lang.${text.from}` as MessageKey) })}</span>}
      {text.revised && lang === 'en' && <span className={`${s.badge} ${s.badgeRevised}`} title={t('lore.badge.revised')}>{t('lore.badge.revised')}</span>}
    </>
  );
}

function TextBlock({ text, lang, names, self, used, showLabel = true }: {
  text: ResolvedText; lang: ContentLang; names?: ReadonlyMap<string, string>; self: string; used: Set<string>; showLabel?: boolean;
}) {
  const { t } = useI18n();
  const labelKey = `lore.field.${text.key}`;
  const label = text.extra?.heading ?? (showLabel && hasKey(labelKey) ? t(labelKey) : null);
  return (
    <section className={s.textBlock} lang={text.from ?? lang}>
      {(label || text.from || text.revised) && (
        <div className={s.textHead}>
          {label && <h3 className={s.fieldLabel}>{label}</h3>}
          <Badges text={text} lang={lang} />
        </div>
      )}
      <RichText text={text.text} markdown={text.extra?.md} names={names} self={self} used={used} />
    </section>
  );
}

function LinkLists({ links }: { links?: Links }) {
  const { t } = useI18n();
  if (!links) return null;
  const rank = (k: string) => { const i = LINK_ORDER.indexOf(k); return i < 0 ? LINK_ORDER.length : i; };
  const keys = Object.keys(links).sort((a, b) => rank(a) - rank(b));
  return (
    <div className={s.links}>
      {keys.map(k => {
        const labelKey = `lore.links.${k}`;
        return (
          <div key={k} className={s.linkGroup}>
            <h4>{hasKey(labelKey) ? t(labelKey) : k} <span className={s.count}>{links[k].length}</span></h4>
            <ul>{links[k].slice(0, 200).map(([ref, title]) => <li key={ref}><Link to={refPath(ref)}>{title}</Link></li>)}</ul>
          </div>
        );
      })}
    </div>
  );
}

/** Fiche d'une entrée : textes dans la langue du contenu (repli signalé), éléments, liens. */
export function EntryView({ section, id, list, lang, meta }: Props) {
  const { t } = useI18n();
  const row = list?.rows.find(r => r[0] === id);
  const hiddenIndex = useAsync(() => (isHidden(section) ? loadHiddenIndex(section) : undefined), [section]);
  const hiddenChunk = hiddenIndex.data ? chunkForId(id, hiddenIndex.data.first) : undefined;
  const chunk = isHidden(section) ? (hiddenChunk !== undefined && hiddenChunk >= 0 ? hiddenChunk : undefined) : row?.[2];
  const bodies = useAsync<Partial<Record<ContentLang, Body>>>(() => {
    if (chunk === undefined) return undefined;
    return loadChunk(lang, section, chunk).then(async data => {
      const own = data[id];
      const out: Partial<Record<ContentLang, Body>> = { [lang]: own };
      for (const other of neededFallbacks(own, lang)) {
        out[other] = (await loadChunk(other, section, chunk))[id];
      }
      return out;
    });
  }, [lang, section, chunk, id]);
  const namesData = useAsync(() => loadNames(lang), [lang]);
  const names = useMemo(() => namesData.data ? new Map(Object.entries(namesData.data)) : undefined, [namesData.data]);
  const body = bodies.data ? resolveBody(bodies.data, lang) : undefined;
  const own = bodies.data?.[lang];
  const title = row?.[4] ?? own?.n ?? id;
  const flags = row?.[3] ?? own?.g ?? 0;
  const self = `${section}/${id}`;
  const used = new Set<string>();

  useEffect(() => {
    const previous = document.title;
    document.title = loreEntryTitle(title, t(`lore.section.${section}` as MessageKey));
    return () => { document.title = previous; };
  }, [title, section, t]);

  const located = row || (isHidden(section) && (hiddenIndex.loading || bodies.loading || own));
  if (!located) return <div className={s.entry}><p className={s.empty}>{t('lore.notFound')}</p></div>;
  const community = Boolean(flags & FLAG_COMMUNITY);
  const bodyMeta = body?.meta;

  return (
    <article className={s.entry} data-testid="lore-entry" lang={lang}>
      {!isHidden(section) && <Link to={lorePath({ view: 'section', section })} className={s.backToList}>‹ {t('lore.backToList')}</Link>}
      <header className={s.entryHead}>
        <h2 className={s.entryTitle}>{title}</h2>
        {body?.subtitle && <p className={s.entrySub}>{body.subtitle}</p>}
        {community && (
          <div className={s.communityBox}>
            <span className={`${s.badge} ${s.badgeCommunity}`}>{t('lore.badge.community')}</span>
            {bodyMeta?.name_official === false && <span className={`${s.badge} ${s.badgeRevised}`}>{t('lore.badge.unofficialName')}</span>}
            {lang !== 'ru' && <p>{t('lore.translatedBy')}</p>}
            <p className={s.creditLine}>{t('lore.credit')} <a href={meta.credit.url} target="_blank" rel="noopener noreferrer">{meta.credit.line}</a></p>
            {bodyMeta?.source && <p className={s.sourceLine}>{t('lore.source')} {bodyMeta.source}</p>}
          </div>
        )}
      </header>
      {bodies.loading && !body && <p className={s.empty}>{t('lore.loading')}</p>}
      {body && (
        <>
          {body.facts && (
            <dl className={s.facts}>
              {body.facts.map(([k, v]) => (
                <div key={k}><dt>{hasKey(`lore.fact.${k}`) ? t(`lore.fact.${k}` as MessageKey) : k}</dt><dd>{v}</dd></div>
              ))}
            </dl>
          )}
          {body.texts.map((text, i) => <TextBlock key={i} text={text} lang={lang} names={names} self={self} used={used} />)}
          {body.items.length > 0 && (
            <div className={s.items}>
              <h3 className={s.itemsTitle}>{t(section === 'secrets' ? 'lore.steps' : section === 'library' ? 'lore.pages' : 'lore.dialogues')}</h3>
              {body.items.map((item, i) => (
                <section key={i} className={s.item}>
                  {item.step && <h4 className={s.itemHead}>{t('lore.step', { n: item.step })}</h4>}
                  {item.heading && (
                    <div className={s.itemHead}>
                      <RichText text={item.heading.text} names={names} self={self} used={used} />
                      <Badges text={item.heading} lang={lang} />
                    </div>
                  )}
                  {item.texts.map((text, j) => <TextBlock key={j} text={text} lang={lang} names={names} self={self} used={used} showLabel={section === 'secrets'} />)}
                  <LinkLists links={item.links} />
                </section>
              ))}
            </div>
          )}
          <LinkLists links={body.links} />
        </>
      )}
    </article>
  );
}
