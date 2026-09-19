import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MESSAGES } from './messages';
import { I18nProvider, detectLang, format, pick, useI18n, LANG_KEY } from './index';

describe('messages', () => {
  it('toutes les clés françaises existent en anglais, et réciproquement', () => {
    expect(Object.keys(MESSAGES.en).sort()).toEqual(Object.keys(MESSAGES.fr).sort());
  });
});

describe('detectLang', () => {
  const storage = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); } } as unknown as Storage;
  };
  it("`?lang=en` gagne et se mémorise ; sinon le choix mémorisé ; sinon le navigateur, français par défaut", () => {
    const s = storage();
    expect(detectLang(s, '?v=8.0&lang=en', 'fr-FR')).toBe('en');
    expect(s.getItem(LANG_KEY)).toBe('en');
    expect(detectLang(s, '', 'fr-FR')).toBe('en');
    expect(detectLang(storage(), '', 'en-GB')).toBe('en');
    expect(detectLang(storage(), '', 'de-DE')).toBe('fr');
    expect(detectLang(storage(), '?lang=klingon', undefined)).toBe('fr');
  });
});

describe('format / pick', () => {
  it('interpole les variables et choisit la langue avec repli sur le français', () => {
    expect(format('À propos de {label}', { label: 'X' })).toBe('À propos de X');
    expect(format('{a} {b}', { a: 1 })).toBe('1 {b}');
    expect(pick({ fr: 'bonjour', en: 'hello' }, 'en')).toBe('hello');
    expect(pick({ fr: 'bonjour' }, 'en')).toBe('bonjour');
    expect(pick(undefined, 'fr')).toBeUndefined();
  });
});

function Probe() {
  const { lang, t } = useI18n();
  return <span data-testid="probe">{lang}:{t('theme.play')}</span>;
}

describe('I18nProvider', () => {
  it('fournit la langue initiale et traduit ; hors provider, français', () => {
    expect(render(<I18nProvider initial="en" storage={null}><Probe /></I18nProvider>).getByTestId('probe').textContent).toBe('en:Play theme');
    expect(render(<Probe />).getAllByTestId('probe').at(-1)?.textContent).toBe('fr:Lire le thème');
  });
});
