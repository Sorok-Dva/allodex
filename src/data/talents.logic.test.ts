import { describe, expect, it, vi } from 'vitest';
import {
  boardOffset, bookPrereqs, fieldGroups, fieldPrereqs, formatVar, internalName, parseGameText, placeAxis, placeWidget,
  resolveSelection, talentName, talentsFile, textFor,
} from './talents.logic';
import { clearTalentsCache, loadJson } from './talents.api';
import type { ClassTalents, TalentField, TalentsIndex } from './talents.types';

const index: TalentsIndex = {
  versions: [
    { id: '2.0', label: '2.0.04', client: 'EN', languages: ['en'], format: 'v1', classes: [
      { code: 'MAGE', slug: 'mage', name: { en: 'Mage' }, talents: 1, layers: 1, fields: 0, systems: [], missingNames: 0 },
    ] },
    { id: '17.0', label: '17.0', client: 'RU', languages: ['en', 'ru'], format: 'v2', classes: [
      { code: 'WARRIOR', slug: 'warrior', name: { en: 'Warrior' }, talents: 1, layers: 1, fields: 1, systems: [], missingNames: 0 },
      { code: 'MAGE', slug: 'mage', name: { en: 'Mage' }, talents: 1, layers: 1, fields: 1, systems: [], missingNames: 0 },
    ] },
    { id: '5.0', label: '5.0', client: '', languages: [], format: 'v1', classes: [] },
  ],
  unavailable: [],
};

const data: ClassTalents = {
  version: '17.0', code: 'WARRIOR', ref: '#1', name: { en: 'Warrior', ru: 'Воин' }, languages: ['en', 'ru'], format: 'v2',
  book: { ref: '#2', layers: [
    { points: 0, cells: [{ type: 'TalentSpell', talent: 't1' }, null, null, null] },
    { points: 4, cells: [null, { type: 'TalentSpell', talent: 't2', parent: 't1' }, null, null] },
  ] },
  fields: [{
    ref: '#3', name: { en: 'Fighter' }, icon: null, start: [1, 1],
    rows: [
      [null, { type: 'TalentAbility', talent: 't3' }, { type: 'TalentAbility', talent: 't3' }],
      [null, { type: 'TalentSpell', talent: 't1' }, { type: 'TalentAbility', talent: 't3' }],
      [{ type: 'TalentAbility', talent: 't3' }, null, null],
    ],
  }],
  talents: {
    t1: { kind: 'spell', ref: '#10', name: { en: 'Strike' }, ranks: [{ ref: '#10' }] },
    t2: { kind: 'spell', ref: 'Mechanics/Spells/War63/Spells/PowerAttack/Spell01.(SpellSingleTarget).xdb', name: {}, ranks: [{ ref: 'x' }] },
    t3: { kind: 'ability', ref: '#12', name: { ru: 'Ярость' }, ranks: [{ ref: 'a' }, { ref: 'b' }, { ref: 'c' }] },
  },
};

describe('textes', () => {
  it('replie sur fr, puis en, puis ru', () => {
    expect(textFor({ ru: 'Воин', en: 'Warrior' }, 'fr')).toEqual({ text: 'Warrior', lang: 'en' });
    expect(textFor({ ru: 'Воин' }, 'en')).toEqual({ text: 'Воин', lang: 'ru' });
    expect(textFor({ fr: 'Guerrier', en: 'Warrior' }, 'en')).toEqual({ text: 'Warrior', lang: 'en' });
    expect(textFor({}, 'fr')).toBeNull();
  });

  it('nom interne tiré de la ressource quand le texte manque', () => {
    expect(internalName('Mechanics/Spells/War63/Spells/PowerAttack/Spell01.(SpellSingleTarget).xdb')).toBe('PowerAttack');
    expect(internalName('Mechanics/Abilities/MageTalents/FireStarter/Ability01.xdb')).toBe('FireStarter');
    expect(internalName('Mechanics/Talents/Fire.xdb')).toBe('Fire');
    expect(internalName('#2259')).toBe('#2259');
    expect(talentName(data.talents.t2, 'fr')).toEqual({ text: 'PowerAttack', lang: null, internal: true });
  });

  it('découpe les balises du jeu et substitue les variables', () => {
    const segs = parseGameText('<html><tip_green>Deals</tip_green> <r name="var0"/> dmg<br/>\r\nnext <p>x</p></html>', { var0: { value: 12.5 } }, 'fr');
    expect(segs).toEqual([
      { kind: 'text', text: 'Deals', tone: 'green' },
      { kind: 'text', text: ' ', tone: undefined },
      { kind: 'var', name: 'var0', value: '12,5', scaled: false, tone: undefined },
      { kind: 'text', text: ' dmg', tone: undefined },
      { kind: 'br' },
      { kind: 'text', text: ' next ', tone: undefined },
      { kind: 'text', text: 'x', tone: undefined },
    ]);
    const unknown = parseGameText('<r name="nope"/>', {}, 'en');
    expect(unknown).toEqual([{ kind: 'var', name: 'nope', value: null, scaled: false, tone: undefined }]);
  });

  it('marque les valeurs soumises à des formules', () => {
    expect(formatVar({ value: 1, scalers: [{ type: 'ScalerDescriptionFormula' }] }, 'en')).toEqual({ text: '1', scaled: true });
    expect(formatVar({ value: null }, 'en')).toBeNull();
  });
});

describe('grilles et prérequis', () => {
  it('regroupe les cases contiguës d’un même talent (une case par rang)', () => {
    const groups = fieldGroups(data.fields[0].rows);
    expect(groups.map(g => [g.talent, g.cells.length])).toEqual([['t3', 3], ['t1', 1], ['t3', 1]]);
  });

  it('centre une grille plus petite sur le damier 9 × 9', () => {
    expect(boardOffset(data.fields[0])).toEqual([3, 3]);
    const f79: TalentField = { ref: '', name: {}, icon: null, rows: Array.from({ length: 9 }, () => Array(7).fill(null)) };
    expect(boardOffset(f79)).toEqual([0, 1]);
  });

  it('prérequis du livre : palier et talent parent', () => {
    expect(bookPrereqs(data, 0, 0)).toEqual([]);
    expect(bookPrereqs(data, 1, 1)).toEqual([{ kind: 'points', points: 4 }, { kind: 'parent', talent: 't1' }]);
    expect(bookPrereqs(data, 1, 0)).toEqual([]);
  });

  it('prérequis de grille : case de départ et nombre de cases', () => {
    expect(fieldPrereqs(data.fields[0], 1, 1)).toEqual([{ kind: 'fieldStart' }]);
    expect(fieldPrereqs(data.fields[0], 0, 1)).toEqual([{ kind: 'fieldRanks', count: 3 }]);
    expect(fieldPrereqs(data.fields[0], 0, 0)).toEqual([]);
  });
});

describe('sélection', () => {
  it('prend la version et la classe de l’URL, sinon la dernière version lisible et sa première classe', () => {
    expect(resolveSelection(index, '2.0', 'mage')).toMatchObject({ version: { id: '2.0' }, slug: 'mage' });
    expect(resolveSelection(index, null, null)).toMatchObject({ version: { id: '17.0' }, slug: 'warrior' });
    expect(resolveSelection(index, '17.0', 'bard')).toMatchObject({ slug: 'warrior' });
    expect(resolveSelection(index, '5.0', null)).toMatchObject({ version: { id: '17.0' } });
    expect(resolveSelection({ versions: [], unavailable: [] }, null, null)).toEqual({ version: null, slug: null });
    expect(talentsFile('17.0', 'warrior')).toBe('/game/talents/17.0/warrior.json');
  });
});

describe('placement des widgets', () => {
  it('suit les quatre alignements du client', () => {
    expect(placeAxis({ align: 'low', pos: 89, size: 59 }, 468)).toEqual([89, 59]);
    expect(placeAxis({ align: 'high', high: 41, size: 52 }, 508)).toEqual([415, 52]);
    expect(placeAxis({ align: 'center', pos: -20, size: 270 }, 508)).toEqual([99, 270]);
    expect(placeAxis({ align: 'both', pos: 48, high: 45 }, 270)).toEqual([48, 177]);
    expect(placeWidget({ x: { align: 'both' }, y: { align: 'both' } }, 508, 749)).toEqual({ x: 0, y: 0, w: 508, h: 749 });
  });
});

describe('chargement', () => {
  it('met en cache les JSON et oublie les échecs', async () => {
    clearTalentsCache();
    const fetcher = vi.fn(async (url: string) => (url.endsWith('ok.json')
      ? new Response(JSON.stringify({ a: 1 }), { status: 200 })
      : new Response('no', { status: 404 }))) as unknown as typeof fetch;
    await expect(loadJson('/x/ok.json', fetcher)).resolves.toEqual({ a: 1 });
    await expect(loadJson('/x/ok.json', fetcher)).resolves.toEqual({ a: 1 });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await expect(loadJson('/x/ko.json', fetcher)).rejects.toThrow('404');
    await expect(loadJson('/x/ko.json', fetcher)).rejects.toThrow('404');
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});
