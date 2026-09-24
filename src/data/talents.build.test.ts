import { describe, expect, it } from 'vitest';
import {
  addBook, addField, bookBlock, checkShared, decodeBuilds, encodeBuilds, linkedTalents, bookSpent, decodeBuild, emptyBuild, encodeBuild, fieldBlock, fieldSpent, fieldTalentRank,
  normalize, removeBook, removeField, rulesFor, spentBeforeRow, type Build, type Calc,
} from './talents.build';
import type { ClassTalents, TalentCell, TalentsIndex } from './talents.types';

const spell = (talent: string, parent?: string): TalentCell => ({ type: 'TalentSpell', talent, ...(parent ? { parent } : {}) });
const ab = (talent: string): TalentCell => ({ type: 'TalentAbility', talent });
const three = [{ ref: 'a' }, { ref: 'b' }, { ref: 'c' }];

/** Livre 3 couches (paliers 0, 4, 8), une grille 3 × 3 de départ central, une grille 3 × 3 au centre vide. */
const data: ClassTalents = {
  version: '17.0', code: 'WARRIOR', ref: '#1', name: { en: 'Warrior' }, languages: ['en'], format: 'v2',
  book: { ref: '#2', layers: [
    { points: 0, cells: [spell('s1'), spell('s2'), spell('s3'), null] },
    { points: 4, cells: [spell('s4', 's1'), null, null, spell('s5')] },
    { points: 8, cells: [null, spell('s6'), null, null] },
  ] },
  fields: [
    { ref: '#3', name: {}, icon: null, start: [1, 1], rows: [
      [ab('a1'), ab('a1'), null],
      [null, spell('c'), ab('a2')],
      [ab('a3'), ab('a3'), ab('a2')],
    ] },
    { ref: '#4', name: {}, icon: null, rows: [
      [null, ab('b1'), null],
      [ab('b2'), null, ab('b3')],
      [null, null, null],
    ] },
  ],
  talents: Object.fromEntries(['s1', 's2', 's3', 's4', 's5', 's6', 'a1', 'a2', 'a3', 'c', 'b1', 'b2', 'b3'].map(k => [k, { kind: 'spell' as const, ref: k, name: {}, ranks: three }])),
};

const calc17: Calc = { data, rules: rulesFor({ book: 82, field: 77 }) };
const calcOld: Calc = { data: { ...data, version: '9.0' }, rules: rulesFor(null) };

function apply(_calc: Calc, build: Build, ...steps: ((b: Build) => Build | null)[]): Build {
  return steps.reduce((b, step) => {
    const next = step(b);
    if (!next) throw new Error('étape refusée');
    return next;
  }, build);
}

describe('règles par version', () => {
  it('17.0 : 82/77 points, première couche au rang 1, coûts 1/2/3', () => {
    expect(calc17.rules).toMatchObject({ bookPoints: 82, fieldPoints: 77, bookStartRank: true, rankCost: [1, 2, 3] });
  });
  it('version sans total connu : pas de plafond, première couche offerte quand même', () => {
    expect(calcOld.rules).toMatchObject({ bookPoints: null, fieldPoints: null, bookStartRank: true });
    expect(emptyBuild(calcOld).book[0]).toEqual([1, 1, 1, 0]);
  });
});

describe('livre', () => {
  it('état de départ 17.0 : sorts de la première couche au rang 1, gratuits', () => {
    const b = emptyBuild(calc17);
    expect(b.book[0]).toEqual([1, 1, 1, 0]);
    expect(bookSpent(calc17, b)).toBe(0);
    expect(spentBeforeRow(calc17, b, 1)).toBe(3);
    expect(removeBook(calc17, b, 0, 0)).toBeNull();
  });

  it('coût croissant des rangs et palier de la couche suivante', () => {
    let b = emptyBuild(calcOld);
    expect(spentBeforeRow(calcOld, b, 1)).toBe(3); // 3 sorts offerts au rang 1
    expect(bookBlock(calcOld, b, 1, 3)).toBe('threshold');
    b = apply(calcOld, b, x => addBook(calcOld, x, 0, 1));
    expect(b.book[0][1]).toBe(2);
    expect(bookSpent(calcOld, b)).toBe(2); // rang 2 : 2 points
    expect(bookBlock(calcOld, b, 1, 3)).toBeNull(); // 1 + 3 + 1 = 5 ≥ 4
    b = apply(calcOld, b, x => addBook(calcOld, x, 0, 1));
    expect(bookSpent(calcOld, b)).toBe(5); // + rang 3 : 3 points
  });

  it('un enfant ne dépasse pas le rang de son parent', () => {
    let b = apply(calcOld, emptyBuild(calcOld), x => addBook(calcOld, x, 0, 1, true));
    expect(bookBlock(calcOld, b, 1, 0)).toBeNull(); // parent au rang 1
    b = apply(calcOld, b, x => addBook(calcOld, x, 1, 0));
    expect(bookBlock(calcOld, b, 1, 0)).toBe('parent');
  });

  it('Maj + clic prend tous les rangs permis ; retrait en cascade (parent, palier)', () => {
    let b = apply(calcOld, emptyBuild(calcOld), x => addBook(calcOld, x, 0, 1, true));
    expect(b.book[0][1]).toBe(3);
    b = apply(calcOld, b, x => addBook(calcOld, x, 0, 0, true), x => addBook(calcOld, x, 1, 0, true));
    expect(b.book[1][0]).toBe(3);
    b = apply(calcOld, b, x => removeBook(calcOld, x, 0, 0));
    expect(b.book[1][0]).toBe(2); // ramené au rang du parent
    b = apply(calcOld, b, x => removeBook(calcOld, x, 0, 1, true), x => removeBook(calcOld, x, 0, 0, true));
    expect(b.book[0]).toEqual([1, 1, 1, 0]);
    expect(b.book[1]).toEqual([0, 0, 0, 0]); // palier perdu (3 < 4)
  });

  it('plafond de points 17.0', () => {
    const tight: Calc = { data, rules: { ...calc17.rules, bookPoints: 2 } };
    const b = apply(tight, emptyBuild(tight), x => addBook(tight, x, 0, 0));
    expect(bookSpent(tight, b)).toBe(2);
    expect(bookBlock(tight, b, 0, 1)).toBe('points');
  });
});

describe('grilles', () => {
  it('départ appris d\'office et gratuit ; seules les cases voisines sont accessibles', () => {
    const b = emptyBuild(calc17);
    expect(b.fields[0][1][1]).toBe(true);
    expect(fieldSpent(calc17, b)).toBe(0);
    expect(fieldBlock(calc17, b, 0, 0, 1)).toBeNull();
    expect(fieldBlock(calc17, b, 0, 0, 0)).toBe('isolated');
    expect(removeField(calc17, b, 0, 1, 1)).toBeNull();
  });

  it('départ vide : il sert d\'ancre sans être appris', () => {
    const b = emptyBuild(calc17);
    expect(b.fields[1][1][1]).toBe(false);
    expect(fieldBlock(calc17, b, 1, 0, 1)).toBeNull();
    expect(fieldBlock(calc17, b, 1, 1, 1)).toBe('empty');
  });

  it('case vide : elle s\'apprend pour 1 point et ouvre le passage vers les rubis voisins', () => {
    // Grille 0 : (1,0) est vide, (0,0) n'est accessible qu'en passant par (1,0) ou (0,1).
    let b = apply(calc17, emptyBuild(calc17), x => addField(calc17, x, 0, 1, 0));
    expect(b.fields[0][1][0]).toBe(true);
    expect(fieldSpent(calc17, b)).toBe(1);
    expect(fieldBlock(calc17, b, 0, 0, 0)).toBeNull();
    expect(fieldBlock(calc17, b, 0, 2, 0)).toBeNull();
    b = apply(calc17, b, x => addField(calc17, x, 0, 2, 0));
    expect(fieldTalentRank(data.fields[0], b.fields[0], 'a3')).toEqual({ current: 1, total: 2 });
    // Le lien partagé garde la case vide ; la retirer détache ce qui en dépendait.
    const code = encodeBuild(calc17, b)!;
    expect(decodeBuild(calc17, code)).toEqual({ ok: true, build: b });
    b = apply(calc17, b, x => removeField(calc17, x, 0, 1, 0));
    expect(b.fields[0][2][0]).toBe(false);
    expect(fieldSpent(calc17, b)).toBe(0);
  });

  it('retirer une case retire celles qui ne sont plus reliées au départ', () => {
    let b = apply(calc17, emptyBuild(calc17), x => addField(calc17, x, 0, 0, 1), x => addField(calc17, x, 0, 0, 0));
    expect(fieldSpent(calc17, b)).toBe(2);
    expect(fieldTalentRank(data.fields[0], b.fields[0], 'a1')).toEqual({ current: 2, total: 2 });
    b = apply(calc17, b, x => removeField(calc17, x, 0, 0, 1));
    expect(b.fields[0][0][0]).toBe(false);
    expect(fieldSpent(calc17, b)).toBe(0);
  });

  it('Maj + clic apprend toutes les cases accessibles du même talent', () => {
    const b = apply(calc17, emptyBuild(calc17), x => addField(calc17, x, 0, 1, 2, true));
    expect(b.fields[0][1][2] && b.fields[0][2][2]).toBe(true);
    expect(fieldSpent(calc17, b)).toBe(2);
  });

  it('plafond des grilles', () => {
    const tight: Calc = { data, rules: { ...calc17.rules, fieldPoints: 1 } };
    const b = apply(tight, emptyBuild(tight), x => addField(tight, x, 0, 0, 1));
    expect(fieldBlock(tight, b, 0, 1, 2)).toBe('points');
  });
});

describe('codage URL', () => {
  const sample = (calc: Calc) => apply(calc, emptyBuild(calc),
    x => addBook(calc, x, 0, 1, true), x => addBook(calc, x, 0, 0), x => addBook(calc, x, 1, 3),
    x => addField(calc, x, 0, 0, 1), x => addField(calc, x, 0, 0, 0), x => addField(calc, x, 1, 1, 0));

  it('aller-retour exact', () => {
    for (const calc of [calc17, calcOld]) {
      const b = sample(calc);
      expect(bookSpent(calc, b)).toBeGreaterThan(0);
      const code = encodeBuild(calc, b)!;
      expect(code.startsWith('1.')).toBe(true);
      expect(decodeBuild(calc, code)).toEqual({ ok: true, build: b });
    }
  });

  it('forme compacte et stable', () => {
    const code = encodeBuild(calc17, sample(calc17));
    expect(code).toBe('1.23100001.D.I');
    expect(encodeBuild(calc17, emptyBuild(calc17))).toBeNull();
  });

  it('rejette les builds invalides', () => {
    expect(decodeBuild(calc17, '2.111')).toEqual({ ok: false, error: 'format' });
    expect(decodeBuild(calc17, '1.1x1')).toEqual({ ok: false, error: 'syntax' });
    expect(decodeBuild(calc17, '1.111.A.A.A')).toEqual({ ok: false, error: 'syntax' }); // grille en trop
    expect(decodeBuild(calc17, '1.' + '1'.repeat(13))).toEqual({ ok: false, error: 'book' }); // trop long
    expect(decodeBuild(calc17, '1.114')).toEqual({ ok: false, error: 'book' }); // rang > max
    expect(decodeBuild(calc17, '1.1111')).toEqual({ ok: false, error: 'book' }); // emplacement vide
    expect(decodeBuild(calc17, '1.011')).toEqual({ ok: false, error: 'rules' }); // sous le rang de départ
    expect(decodeBuild(calc17, '1.11100001')).toEqual({ ok: false, error: 'rules' }); // palier non atteint
    expect(decodeBuild(calc17, '1.111.B')).toEqual({ ok: false, error: 'rules' }); // case détachée du départ
    expect(decodeBuild(calc17, '1.111.Q')).toEqual({ ok: false, error: 'grid' }); // départ codé (il est implicite)
    expect(decodeBuild(calc17, '1.111.AI')).toEqual({ ok: false, error: 'grid' }); // bit après la dernière case
    expect(decodeBuild(calc17, '1.111.C').ok).toBe(true); // voisine du départ
    expect(decodeBuild(calc17, '1.111.U')).toEqual({ ok: false, error: 'grid' }); // bit sur une case vide
    expect(decodeBuild(calc17, '1.111.QAAA')).toEqual({ ok: false, error: 'grid' }); // trop long
    const tight: Calc = { data, rules: { ...calc17.rules, bookPoints: 1 } };
    expect(decodeBuild(tight, '1.121')).toEqual({ ok: false, error: 'points' });
  });

  it('normalize ne change pas un build valide', () => {
    const b = sample(calc17);
    expect(normalize(calc17, b)).toEqual(b);
  });
});

describe('deux builds', () => {
  it('b et b2 : aller-retour indépendant, ancien lien à un seul build accepté', () => {
    const one = apply(calc17, emptyBuild(calc17), x => addBook(calc17, x, 0, 0, true));
    const two = apply(calc17, emptyBuild(calc17), x => addField(calc17, x, 0, 0, 1));
    const codes = encodeBuilds(calc17, [one, two]);
    expect(codes).toEqual({ b: '1.311', b2: '1.111.C' });
    expect(decodeBuilds(calc17, codes.b, codes.b2)).toEqual({ builds: [one, two], errors: [null, null] });
    expect(decodeBuilds(calc17, '1.311', null)).toEqual({ builds: [one, emptyBuild(calc17)], errors: [null, null] });
  });
  it('un build invalide est signalé sans toucher à l’autre', () => {
    const one = apply(calc17, emptyBuild(calc17), x => addBook(calc17, x, 0, 0, true));
    expect(decodeBuilds(calc17, '1.311', '9.1')).toEqual({ builds: [one, emptyBuild(calc17)], errors: [null, 'format'] });
  });
});

describe('liens sort ↔ rubis', () => {
  it('les deux sens, sans le talent lui-même', () => {
    const linked: ClassTalents = { ...data, talents: { ...data.talents, a1: { ...data.talents.a1, links: ['s1', 's2', 'a1'] } } };
    expect([...linkedTalents(linked, 'a1')].sort()).toEqual(['s1', 's2']);
    expect([...linkedTalents(linked, 's1')]).toEqual(['a1']);
    expect(linkedTalents(linked, 's3').size).toBe(0);
  });
});

describe('plafonds de l’index (manifeste)', () => {
  const idx = Object.values(import.meta.glob<TalentsIndex>('../../public/game/talents/index.json', { eager: true, import: 'default' }))[0];
  it.skipIf(!idx)('16.0 : 91/80, 17.0 : 82/77 (nets des 3 points offerts), autres sans plafond', () => {
    const pts = Object.fromEntries(idx.versions.map(v => [v.id, v.points ? [v.points.book, v.points.field] : null]));
    expect(pts['16.0']).toEqual([91, 80]);
    expect(pts['17.0']).toEqual([82, 77]);
    expect(Object.entries(pts).filter(([id, p]) => p && id !== '16.0' && id !== '17.0')).toEqual([]);
    const v16 = idx.versions.find(v => v.id === '16.0')!;
    expect(v16.points?.source).toMatch(/16\.0/);
    expect(rulesFor(v16.points)).toMatchObject({ bookPoints: 91, fieldPoints: 80, bookStartRank: true });
  });
});

describe('lien partagé', () => {
  const index: TalentsIndex = {
    versions: [
      { id: '9.0', label: '9.0', client: '', languages: [], format: 'v1', classes: [{ code: 'MAGE', slug: 'mage', name: {}, talents: 1, layers: 1, fields: 3, systems: [], missingNames: 0 }] },
      { id: '17.0', label: '17.0', client: '', languages: [], format: 'v2', classes: [{ code: 'WARRIOR', slug: 'warrior', name: {}, talents: 1, layers: 1, fields: 3, systems: [], missingNames: 0 }] },
    ],
    unavailable: [],
  };
  it('version ou classe inconnue : le build est refusé', () => {
    expect(checkShared(index, '17.0', 'warrior')).toBeNull();
    expect(checkShared(index, '42.0', 'warrior')).toBe('version');
    expect(checkShared(index, null, 'warrior')).toBe('version');
    expect(checkShared(index, '9.0', 'warrior')).toBe('class');
  });
});

describe('données réelles 17.0', () => {
  const files = import.meta.glob<ClassTalents>('../../public/game/talents/17.0/druid.json', { eager: true, import: 'default' });
  const real = Object.values(files)[0];
  it.skipIf(!real)('un build complet tient dans 82/77 et fait l\'aller-retour', () => {
    const calc: Calc = { data: real, rules: rulesFor({ book: 82, field: 77 }) };
    let b = emptyBuild(calc);
    // Remplit le livre couche par couche puis les grilles tant que c'est permis.
    for (let guard = 0; guard < 500; guard++) {
      let moved = false;
      for (let r = 0; r < real.book.layers.length && !moved; r++) for (let c = 0; c < 4 && !moved; c++) {
        const next = addBook(calc, b, r, c);
        if (next) { b = next; moved = true; }
      }
      for (let f = 0; f < real.fields.length && !moved; f++) real.fields[f].rows.forEach((row, r) => row.forEach((_, c) => {
        if (moved) return;
        const next = addField(calc, b, f, r, c);
        if (next) { b = next; moved = true; }
      }));
      if (!moved) break;
    }
    expect(bookSpent(calc, b)).toBeLessThanOrEqual(82);
    expect(bookSpent(calc, b)).toBeGreaterThan(70);
    expect(fieldSpent(calc, b)).toBe(77);
    const code = encodeBuild(calc, b)!;
    expect(code.length).toBeLessThan(90);
    expect(decodeBuild(calc, code)).toEqual({ ok: true, build: b });
  });
});
