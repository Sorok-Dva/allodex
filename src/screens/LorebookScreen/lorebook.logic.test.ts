import { describe, expect, it } from 'vitest';
import {
  chunkForId, decodeIds, decodePostings, linkNames, listRows, lorePath, neededFallbacks, normalize, paragraphs, parseLoreRoute,
  parseMarkdown, queryTokens, refPath, resolveBody, searchIndex, shardKey, visibleRange,
  type Body, type ListData, type Shard,
} from './lorebook.logic';

const q = (s: string) => new URLSearchParams(s);

describe('routes', () => {
  it('lit et reconstruit les URL stables des sections, entrées et recherches', () => {
    expect(parseLoreRoute('/lorebook', q(''))).toEqual({ view: 'home' });
    expect(parseLoreRoute('/lorebook/', q(''))).toEqual({ view: 'home' });
    expect(parseLoreRoute('/lorebook/quests', q('group=zone-Kania'))).toEqual({ view: 'section', section: 'quests', group: 'zone-Kania' });
    expect(parseLoreRoute('/lorebook/secrets/r294735', q(''))).toEqual({ view: 'entry', section: 'secrets', id: 'r294735' });
    expect(parseLoreRoute('/lorebook/search', q('q=Zayan'))).toEqual({ view: 'search', q: 'Zayan' });
    expect(parseLoreRoute('/lorebook/unknown/x', q(''))).toEqual({ view: 'home' });
    for (const route of [
      { view: 'section', section: 'atlas', group: 'regions' },
      { view: 'entry', section: 'library', id: 'c-memories-of-catherina' },
      { view: 'search', q: 'Смеяна & co' },
    ] as const) {
      const url = new URL(lorePath(route), 'http://x');
      expect(parseLoreRoute(url.pathname, url.searchParams)).toEqual(route);
    }
    expect(refPath('characters/r20')).toBe('/lorebook/characters/r20');
    expect(refPath('nope/r20')).toBe('/lorebook');
    expect(parseLoreRoute('/lorebook/dialogues/r31', q(''))).toEqual({ view: 'entry', section: 'dialogues', id: 'r31' });
  });

  it('retrouve le bloc d’une entrée cachée par dichotomie sur le premier rid des blocs', () => {
    const firsts = [5, 100, 2000];
    expect(chunkForId('r5', firsts)).toBe(0);
    expect(chunkForId('r99', firsts)).toBe(0);
    expect(chunkForId('r100', firsts)).toBe(1);
    expect(chunkForId('r999999', firsts)).toBe(2);
    expect(chunkForId('r4', firsts)).toBe(-1);
    expect(chunkForId('c-x', firsts)).toBe(-1);
  });
});

describe('repli des langues du contenu', () => {
  const en: Body = { t: [['goal', 0, 0], ['startText', 'Listen, hero.', 1]], i: [{ h: ['name', 0, 0], t: [['text', 'Hi', 0]] }] };
  const fr: Body = { t: [['goal', 'Tuez les loups.', 0], ['startText', 'Écoute, héros.', 0]], i: [{ h: ['name', 0, 0], t: [['text', 'Salut', 0]] }] };
  const ru: Body = { t: [['goal', 'Убить волков.', 0], ['startText', 'Слушай.', 0]], i: [{ h: ['name', 'Кто ты?', 0], t: [['text', 'Привет', 0]] }] };

  it('ne charge les autres langues que si un texte manque', () => {
    expect(neededFallbacks(en, 'en')).toEqual(['fr', 'ru']);
    expect(neededFallbacks(fr, 'fr')).toEqual(['en', 'ru']);
    expect(neededFallbacks({ t: [['goal', 'x', 0]] }, 'en')).toEqual([]);
    expect(neededFallbacks(undefined, 'en')).toEqual([]);
  });

  it("prend l'anglais, sinon le français, sinon le russe, et le signale", () => {
    const body = resolveBody({ en, fr, ru }, 'en')!;
    expect(body.texts[0]).toMatchObject({ key: 'goal', text: 'Tuez les loups.', from: 'fr', revised: false });
    expect(body.texts[1]).toMatchObject({ text: 'Listen, hero.', from: null, revised: true });
    expect(body.items[0].heading).toMatchObject({ text: 'Кто ты?', from: 'ru' });
    const inFr = resolveBody({ en, fr, ru }, 'fr')!;
    expect(inFr.texts[1]).toMatchObject({ text: 'Écoute, héros.', from: null, revised: false });
    const inRu = resolveBody({ ru }, 'ru')!;
    expect(inRu.texts.map(t => t.from)).toEqual([null, null]);
  });
});

describe('recherche', () => {
  const stop = new Set(['the']);
  it('normalise comme l’outil et écarte mots courts et vides', () => {
    expect(normalize('Élégie de Ёлка')).toBe('elegie de елка');
    expect(queryTokens('The Great  Ёлка ab great', stop)).toEqual(['great', 'елка']);
    expect(shardKey('кания')).toBe('43a430');
    expect(shardKey('wolf')).toBe('776f');
  });

  it('décode les listes de postings en base 36 à écarts', () => {
    expect(decodeIds('3,2,z')).toEqual([3, 5, 40]);
    expect(decodeIds('')).toEqual([]);
    expect(decodePostings('1,1|2')).toEqual({ all: [1, 2], title: [2] });
  });

  it('intersecte les mots, préfixe le dernier, classe les titres devant', () => {
    const shards: Record<string, Shard> = {
      [shardKey('wolf')]: { wolf: '1,1,1|3', wolves: '5' },
      [shardKey('threat')]: { threat: '2,1' },
    };
    const hits = searchIndex(['wolf', 'threat'], shards);
    expect(hits.map(h => h.gid)).toEqual([3, 2]);           // 3 : « wolf » dans le titre
    expect(searchIndex(['wol'], shards).map(h => h.gid).sort((a, b) => a - b)).toEqual([1, 2, 3, 5]);
    expect(searchIndex(['absent'], shards)).toEqual([]);
    expect(searchIndex([], shards)).toEqual([]);
  });
});

describe('liens automatiques', () => {
  const names = new Map([['Catherina', 'characters/r20'], ['Great Mage Zayan', 'characters/r30'], ['Zayan', 'characters/r31'], ['Kania', 'atlas/a-a001']]);
  it('lie le nom le plus long, une fois par cible, jamais l’entrée elle-même', () => {
    const segs = linkNames('Great Mage Zayan met Catherina in Kania. Catherina left; Zayan stayed.', names, 'atlas/a-a001');
    expect(segs.filter(s => s.ref)).toEqual([
      { text: 'Great Mage Zayan', ref: 'characters/r30' },
      { text: 'Catherina', ref: 'characters/r20' },
      { text: 'Zayan', ref: 'characters/r31' },
    ]);
    expect(segs.map(s => s.text).join('')).toBe('Great Mage Zayan met Catherina in Kania. Catherina left; Zayan stayed.');
    expect(linkNames('plain', new Map())).toEqual([{ text: 'plain' }]);
  });
});

describe('liste virtualisée et textes', () => {
  const list: ListData = {
    groups: [{ id: 'a', key: 'lore.group.events', count: 2 }, { id: 'b', label: 'Kania', count: 1 }],
    rows: [['r1', 0, 0, 0, 'One', ''], ['r2', 0, 0, 0, 'Two', ''], ['r3', 1, 0, 0, 'Three', '']],
  };
  it('insère les en-têtes de groupe et filtre par groupe', () => {
    const rows = listRows(list, g => g.label ?? g.id);
    expect(rows.map(r => r.kind)).toEqual(['group', 'entry', 'entry', 'group', 'entry']);
    expect(listRows(list, g => g.id, 1)).toEqual([{ kind: 'group', group: 1, label: 'b', count: 1 }, { kind: 'entry', index: 2 }]);
  });
  it('ne rend que les lignes visibles, avec une marge', () => {
    expect(visibleRange(0, 520, 52, 10000)).toEqual([0, 18]);
    expect(visibleRange(52 * 500, 520, 52, 10000)).toEqual([492, 518]);
    expect(visibleRange(52 * 9999, 520, 52, 10000)).toEqual([9991, 10000]);
  });
  it('découpe le Markdown des textes communautaires et les paragraphes officiels', () => {
    expect(parseMarkdown('## Old Era\n\n- **(~1)** Start\nof time\n\nText one\nstill one')).toEqual([
      { type: 'h', text: 'Old Era' }, { type: 'li', text: '**(~1)** Start of time' }, { type: 'p', text: 'Text one still one' },
    ]);
    expect(paragraphs('A\n\nB\nC')).toEqual(['A', 'B', 'C']);
  });
});
