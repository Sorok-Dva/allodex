import { useEffect, useRef } from 'react';
import { LanguageSwitcher } from '@/components/controls/LanguageSwitcher';
import { useI18n } from '@/lib/i18n';
import { Link } from '@/lib/router';
import { T, tex } from '@/lib/assets';
import s from './LegalScreen.module.css';

const sections = ['project', 'use', 'rights', 'availability', 'storage', 'audience', 'links', 'changes'] as const;

export function LegalScreen() {
  const { t } = useI18n();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return <main className={s.screen} style={{ backgroundImage: `linear-gradient(#07110ce8, #07110cf5), url(${tex(`${T.main2}/Background_14_0_Temp`)})` }}>
    <article className={s.document}>
      <header className={s.header}><Link to="/">{t('legal.back')}</Link><LanguageSwitcher /></header>
      <h1 ref={heading} tabIndex={-1}>{t('legal.title')}</h1>
      <p className={s.date}>{t('legal.updated')}</p>
      {sections.map(section => <section key={section}>
        <h2>{t(`legal.${section}Title`)}</h2>
        <p>{t(`legal.${section}`)}</p>
        {section === 'links' && <a href="https://p-42.fr/allodex-developer" target="_blank" rel="noopener noreferrer">{t('legal.portfolio')}</a>}
      </section>)}
      <footer>{t('home.copyright', { year: new Date().getFullYear() })} <a href="https://p-42.fr/allodex-developer" target="_blank" rel="noopener noreferrer">Sorok-Dva</a></footer>
    </article>
  </main>;
}
