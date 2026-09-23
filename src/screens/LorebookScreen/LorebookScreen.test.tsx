import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { I18nProvider } from '@/lib/i18n';
import { LorebookScreen, initialContentLang } from './LorebookScreen';
import { clearLoreCache } from './lorebook.data';
import { shardKey } from './lorebook.logic';

const credit = { line: 'Allods atlas and community lore material compiled by Makar Terentiev (DarkyAndSparky), https://github.com/DarkyAndSparky/atlas-ao', url: 'https://github.com/DarkyAndSparky/atlas-ao' };
const sections = Object.fromEntries(['timeline', 'atlas', 'library', 'characters', 'secrets', 'quests'].map(s => [s, { count: 1, chunks: 1, groups: [] }]));
const files: Record<string, unknown> = {
  'meta.json': { sections, credit, translated_by: 'Community text, translated by Allodex', entries: 3, dir_block: 64, token_min: 3, stopwords: ['the'] },
  'list/en/quests.json': { groups: [{ id: 'zone-Kania', label: 'Kania', count: 1 }], rows: [['r10', 0, 0, 2, 'Wolf Threat', '']] },
  'text/en/quests-0.json': { r10: { t: [['goal', 0, 0], ['startText', 'Listen, hero.', 1]], l: { characters: [['characters/r20', 'Catherina']] } } },
  'text/fr/quests-0.json': { r10: { t: [['goal', 'Tuez les loups.', 0], ['startText', 'Écoute, héros.', 0]] } },
  'text/ru/quests-0.json': { r10: { t: [['goal', 'Убить волков.', 0], ['startText', 'Слушай, герой.', 0]] } },
  'list/en/library.json': { groups: [{ id: 'stories', key: 'lore.group.stories', count: 1 }], rows: [['c-memories', 0, 0, 1, 'Memories of Catherina', '']] },
  'text/en/library-0.json': { 'c-memories': { t: [['communityText', '## 13 March\n\nCatherina was born in Scarge.', 0, { md: true }]], m: { credit: credit.line, translated: 'x', source: 'stories/memories.txt' } } },
  'names/en.json': { Catherina: 'characters/r20', Scarge: 'atlas/a-a100' },
  [`search/en/${shardKey('wolf')}.json`]: { wolf: '0|0', wolves: '1' },
  'dir/en/0.json': [['quests', 'r10', 'Wolf Threat', 2], ['characters', 'r21', 'Wolves of Kania', 0]],
};

function go(path: string) {
  window.history.pushState(null, '', path);
}

function mount() {
  return render(<I18nProvider initial="en" storage={null}><LorebookScreen storage={null} /></I18nProvider>);
}

beforeEach(() => {
  clearLoreCache();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const key = url.replace('/game/lorebook/', '');
    return key in files ? { ok: true, status: 200, json: async () => files[key] } : { ok: false, status: 404, json: async () => ({}) };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); go('/'); });

describe('LorebookScreen', () => {
  it("affiche les sections à l'accueil et le crédit en pied de page", async () => {
    go('/lorebook');
    const page = mount();
    await waitFor(() => expect(page.getByTestId('lore-home')).toBeTruthy());
    expect(page.getAllByText('World Secrets').length).toBeGreaterThan(0);
    expect(page.getByRole('link', { name: credit.line }).getAttribute('href')).toBe(credit.url);
  });

  it('montre le repli français avec son badge, le badge de révision et les liens', async () => {
    go('/lorebook/quests/r10');
    const page = mount();
    await waitFor(() => expect(page.getByText('Tuez les loups.')).toBeTruthy());
    expect(page.getByText('Not yet translated — French text')).toBeTruthy();
    expect(page.getAllByText('English may predate a Russian revision').length).toBeGreaterThan(0);
    expect(page.getByText('Listen, hero.')).toBeTruthy();
    expect(page.getByRole('link', { name: 'Catherina' }).getAttribute('href')).toBe('/lorebook/characters/r20');
    // passage au russe : aucun badge de repli
    fireEvent.click(page.getByRole('button', { name: 'RU' }));
    await waitFor(() => expect(page.getByText('Убить волков.')).toBeTruthy());
    expect(page.queryByText(/Not yet translated/)).toBeNull();
  });

  it('crédite un texte communautaire et lie les noms propres', async () => {
    go('/lorebook/library/c-memories');
    const page = mount();
    await waitFor(() => expect(page.getByText('Community text, translated by Allodex')).toBeTruthy());
    expect(page.getAllByText('Community').length).toBeGreaterThan(0);
    await waitFor(() => expect(page.getByRole('link', { name: 'Scarge' }).getAttribute('href')).toBe('/lorebook/atlas/a-a100'));
    expect(page.getByRole('heading', { name: '13 March' })).toBeTruthy();
  });

  it('cherche dans l’index fragmenté et affiche les entrées trouvées', async () => {
    go('/lorebook/search?q=wol');
    const page = mount();
    await waitFor(() => expect(page.getByText('2 results for “wol”')).toBeTruthy());
    const links = page.getByTestId('lore-search').querySelectorAll('a');
    expect([...links].map(a => a.getAttribute('href'))).toEqual(['/lorebook/quests/r10', '/lorebook/characters/r21']);
  });

  it('prend la langue du contenu dans l’URL, puis le choix mémorisé, anglais par défaut', () => {
    const storage = { getItem: () => 'ru', setItem: () => {} } as unknown as Storage;
    expect(initialContentLang('?text=fr', storage)).toBe('fr');
    expect(initialContentLang('', storage)).toBe('ru');
    expect(initialContentLang('', null)).toBe('en');
  });
});
