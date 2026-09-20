import { useI18n } from '@/lib/i18n';
import s from './LanguageSwitcher.module.css';

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  return <div className={s.switcher} role="group" aria-label={t('common.language')}>
    <button type="button" lang="fr" aria-label="Français" aria-pressed={lang === 'fr'} onClick={() => setLang('fr')}>FR</button>
    <span aria-hidden="true">/</span>
    <button type="button" lang="en" aria-label="English" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
  </div>;
}
