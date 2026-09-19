import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { LANGS, MESSAGES, type Lang, type MessageKey } from './messages';

export const LANG_KEY = 'allodex:lang';

/** Texte localisé porté par les données (fiches de version) : une entrée par langue. */
export type Localized<T = string> = Partial<Record<Lang, T>>;

/** Lit une valeur localisée : la langue demandée, sinon le français, sinon l'anglais. */
export function pick<T>(value: Localized<T> | undefined, lang: Lang): T | undefined {
  if (!value) return undefined;
  return value[lang] ?? value.fr ?? value.en;
}

function isLang(value: string | null | undefined): value is Lang {
  return !!value && (LANGS as readonly string[]).includes(value);
}

/**
 * Langue de départ : `?lang=` dans l'URL (mémorisé), sinon le choix mémorisé, sinon la
 * langue du navigateur (anglais → `en`, tout le reste → `fr`, la langue du site).
 */
export function detectLang(storage: Storage | null, search: string, navigatorLang: string | undefined): Lang {
  const fromUrl = new URLSearchParams(search).get('lang');
  if (isLang(fromUrl)) {
    try { storage?.setItem(LANG_KEY, fromUrl); } catch { /* stockage indisponible */ }
    return fromUrl;
  }
  try {
    const stored = storage?.getItem(LANG_KEY);
    if (isLang(stored)) return stored;
  } catch { /* stockage indisponible */ }
  return navigatorLang?.toLowerCase().startsWith('en') ? 'en' : 'fr';
}

/** Interpole `{nom}` dans un message. */
export function format(message: string, vars?: Record<string, string | number>): string {
  if (!vars) return message;
  return message.replace(/\{(\w+)\}/g, (all, key: string) => (key in vars ? String(vars[key]) : all));
}

export type I18n = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children, storage = window.localStorage, initial }: { children: ReactNode; storage?: Storage | null; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(() => initial ?? detectLang(storage, window.location.search, navigator.language));
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try { storage?.setItem(LANG_KEY, next); } catch { /* stockage indisponible */ }
  }, [storage]);
  const t = useCallback((key: MessageKey, vars?: Record<string, string | number>) => format(MESSAGES[lang][key] ?? MESSAGES.fr[key], vars), [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Hors provider (tests unitaires de composants isolés) : français, sans mémorisation. */
const FALLBACK: I18n = { lang: 'fr', setLang: () => {}, t: (key, vars) => format(MESSAGES.fr[key], vars) };

export function useI18n(): I18n {
  return useContext(I18nContext) ?? FALLBACK;
}
