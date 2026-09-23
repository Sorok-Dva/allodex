import { describe, it, expect } from 'vitest';
import type { ChargenData } from '@/data/character/chargen.types';
import type { FatalityCharacter, FatalityEntry } from '@/lib/assets';
import { DEFAULT_TIER, attackerClass, classesOf, dressFor, fatalityClass } from './outfits';

const growth = (id: string) => ({ start: null, loop: null, items: [{ slot: 'ARMOR', item: id }], fx: [] });
const DATA = {
  races: { Kania: { classes: ['BARD', 'WARRIOR'] }, Gibberling: { classes: ['WARRIOR'] } },
  classes: { BARD: {}, WARRIOR: {}, MAGE: {} },
  combos: {
    'Kania/WARRIOR': { sexes: { male: { template: 'KaniaMale', growths: [growth('low'), growth('mid'), growth('high')] } } },
    'Gibberling/WARRIOR': { sexes: { male: { template: 'GibberlingMale', growths: [growth('g0'), growth('g1'), growth('g2')] } } },
  },
} as unknown as ChargenData;
const kania = { id: 'kania-male', race: 'kania', sex: 'male' } as FatalityCharacter;
const gib = { id: 'gibberling-male', race: 'gibberling', sex: 'male' } as FatalityCharacter;
const warrior = { id: 'warrior' } as FatalityEntry;
const lotus = { id: 'lotus' } as FatalityEntry;

describe('tenues des fatalités', () => {
  it('classes de la race, classe de la fatalité pour le tueur si possible', () => {
    expect(classesOf(DATA, 'kania')).toEqual(['BARD', 'WARRIOR']);
    expect(fatalityClass(DATA, warrior)).toBe('WARRIOR');
    expect(fatalityClass(DATA, lotus)).toBeNull();
    expect(attackerClass(DATA, 'kania', warrior)).toBe('WARRIOR');
    expect(attackerClass(DATA, 'kania', lotus)).toBe('BARD');
  });

  it('habit du niveau choisi (supérieur par défaut), trio pour les gibelins', () => {
    const d = dressFor(DATA, '/game/character/', kania, 'WARRIOR', DEFAULT_TIER)!;
    expect(d.template).toBe('KaniaMale');
    expect(d.items).toEqual([{ slot: 'ARMOR', item: 'high' }]);
    expect(d.trio).toBe(false);
    expect(dressFor(DATA, '/game/character/', kania, 'WARRIOR', 0)!.items[0].item).toBe('low');
    expect(dressFor(DATA, '/game/character/', gib, 'WARRIOR', 1)!.trio).toBe(true);
    expect(dressFor(DATA, '/game/character/', kania, 'MAGE', 2)).toBeNull();
    expect(dressFor(null, '/game/character/', kania, 'WARRIOR', 2)).toBeNull();
  });
});
