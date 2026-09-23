import { describe, expect, it } from 'vitest';
import { PAGES, PAGE_IDS, excerpt, metaFor, normalizePath, renderHead } from './meta';

const q = (s = '') => new URLSearchParams(s);

describe('métadonnées des pages', () => {
  it('donne à chaque page un titre et une description de longueur raisonnable, dans les deux langues', () => {
    for (const id of PAGE_IDS) {
      for (const lang of ['fr', 'en'] as const) {
        const { title, description } = PAGES[id][lang];
        expect(title.length, `${id}/${lang}`).toBeLessThanOrEqual(70);
        expect(description.length, `${id}/${lang}`).toBeGreaterThan(50);
        expect(description.length, `${id}/${lang}`).toBeLessThanOrEqual(170);
      }
    }
  });

  it('ramène les alias à la page principale', () => {
    expect(normalizePath('/succes')).toBe('/achievements');
    expect(normalizePath('/cinematiques/')).toBe('/cinematics');
    expect(metaFor('/musiques', q()).canonical).toBe('https://allodex.eu/music');
  });

  it('choisit la langue : paramètre, puis navigateur, puis français', () => {
    expect(metaFor('/talents', q('lang=en')).lang).toBe('en');
    expect(metaFor('/talents', q('lang=en')).canonical).toBe('https://allodex.eu/talents?lang=en');
    expect(metaFor('/talents', q(), { acceptLanguage: 'en-US,en' }).title).toContain('talent calculator');
    expect(metaFor('/talents', q(), { acceptLanguage: 'de-DE' }).lang).toBe('fr');
    expect(metaFor('/talents', q()).alternates.map(a => a.hreflang)).toEqual(['fr', 'en', 'x-default']);
  });

  it('décrit les rubriques et entrées du Lorebook, dans la langue du texte', () => {
    const section = metaFor('/lorebook/atlas', q('text=fr'));
    expect(section.title).toBe('Atlas — Allods Online Lorebook — Allodex');
    expect(section.lang).toBe('fr');
    expect(section.canonical).toBe('https://allodex.eu/lorebook/atlas?text=fr');
    const entry = metaFor('/lorebook/characters/r1', q(), { lore: () => ({ section: 'characters', id: 'r1', title: 'Kanius', description: 'Le héros.' }) });
    expect(entry.title).toBe('Kanius — Characters · Allods Online Lorebook');
    expect(entry.type).toBe('article');
    expect(entry.alternates.map(a => a.href)).toContain('https://allodex.eu/lorebook/characters/r1?text=ru');
    expect(metaFor('/lorebook/characters/r1', q(), { lore: () => undefined }).status).toBe(404);
    expect(metaFor('/lorebook/search', q('q=x')).robots).toBe('noindex,follow');
    expect(metaFor('/lorebook/toString', q()).status).toBe(404);
  });

  it("n'indexe ni les outils internes ni les chemins inconnus", () => {
    expect(metaFor('/stats', q()).robots).toBe('noindex,nofollow');
    expect(metaFor('/stats', q()).status).toBe(200);
    expect(metaFor('/n-importe-quoi', q()).status).toBe(404);
  });

  it('échappe le HTML des balises et du JSON-LD', () => {
    const head = renderHead({ ...metaFor('/', q()), title: 'A "B" <c>', jsonLd: [{ name: '</script><x>' }] });
    expect(head).toContain('<title>A &quot;B&quot; &lt;c&gt;</title>');
    expect(head).toContain('\\u003c/script>');
    expect(head).not.toContain('</script><x>');
  });

  it('coupe les extraits sur une fin de mot', () => {
    expect(excerpt('court')).toBe('court');
    const long = excerpt('mot '.repeat(80), 40);
    expect(long.length).toBeLessThanOrEqual(40);
    expect(long.endsWith('mot…')).toBe(true);
  });
});
