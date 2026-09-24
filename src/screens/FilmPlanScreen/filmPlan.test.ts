import { describe, expect, it } from 'vitest';
import {
  DEFAULT_FILTERS, addFreeEntry, formatSeconds, gapOf, moveEntry, serializePlan, siteLink, stepEntry, timeline, totals, updateEntry, validatePlan,
  type FilmPlan, type PlanEntry,
} from './filmPlan';

function entry(id: string, over: Partial<PlanEntry> = {}): PlanEntry {
  return { id, title: `Scène ${id}`, chapter: 'a', faction: 'common', zone: 'Z', version: '7.0', kind: 'engine', duration: 10, status: 'film', priority: 'none', ...over };
}

function plan(entries: PlanEntry[]): FilmPlan {
  return {
    format: 1, targetMinutes: 90,
    chapters: [
      { id: 'a', title: 'A', version: '1.0', faction: 'common' },
      { id: 'l', title: 'Ligue', version: '1.0', faction: 'league' },
      { id: 'b', title: 'B', version: '2.0', faction: 'common' },
      { id: 'e', title: 'Empire', version: '2.0', faction: 'empire' },
    ],
    entries,
  };
}

describe('validatePlan', () => {
  it('accepte un plan minimal', () => {
    expect(validatePlan(plan([entry('x')]))).toEqual([]);
  });

  it('refuse les structures invalides', () => {
    expect(validatePlan(null)).not.toEqual([]);
    expect(validatePlan({ ...plan([]), format: 2 })).toContain('format attendu : 1');
    const bad = plan([entry('x', { status: 'nope' as never }), entry('x'), entry('y', { chapter: 'zz' }), entry('Z z'), entry('w', { duration: -1 })]);
    const errors = validatePlan(bad).join('\n');
    expect(errors).toMatch(/status/);
    expect(errors).toMatch(/doublon « x »/);
    expect(errors).toMatch(/chapitre inconnu « zz »/);
    expect(errors).toMatch(/entries\[3\]\.id/);
    expect(errors).toMatch(/entries\[4\]\.duration/);
    expect(validatePlan({ ...plan([]), extra: 1 }).join()).toMatch(/clé inconnue : extra/);
    expect(validatePlan(plan([{ ...entry('x'), foo: 1 } as PlanEntry])).join()).toMatch(/clé inconnue foo/);
  });
});

describe('frise', () => {
  const p = plan([
    entry('a1'), entry('a2', { status: 'todo', duration: null }),
    entry('l1', { chapter: 'l', faction: 'league', status: 'todo', duration: 20 }),
    entry('e1', { chapter: 'e', faction: 'empire', duration: 30 }),
    entry('b1', { chapter: 'b', status: 'discarded' }),
    entry('bonus', { chapter: 'b', bonus: true, duration: 99 }),
  ]);

  it('garde, par faction, ses chapitres et les communs', () => {
    expect(timeline(p, 'league').map(c => c.chapter.id)).toEqual(['a', 'l', 'b']);
    expect(timeline(p, 'empire').map(c => c.chapter.id)).toEqual(['a', 'b', 'e']);
    expect(timeline(p, 'all').map(c => c.chapter.id)).toEqual(['a', 'l', 'b', 'e']);
  });

  it('signale les trous', () => {
    const byId = Object.fromEntries(timeline(p, 'all').map(c => [c.chapter.id, c.gap]));
    expect(byId).toEqual({ a: 'none', l: 'partial', b: 'none', e: 'none' });
    expect(gapOf([])).toBe('empty');
    expect(gapOf([entry('d', { status: 'discarded' })])).toBe('empty');
    expect(timeline(p, 'league', { ...DEFAULT_FILTERS, gapsOnly: true }).map(c => c.chapter.id)).toEqual(['l']);
  });

  it('filtre sans cacher les chapitres', () => {
    const t = timeline(p, 'league', { ...DEFAULT_FILTERS, statuses: ['todo'], text: 'scène a' });
    expect(t.find(c => c.chapter.id === 'a')?.shown.map(e => e.id)).toEqual(['a2']);
    expect(t.find(c => c.chapter.id === 'l')?.shown).toEqual([]);
  });

  it('totalise film actuel et film visé, bonus à part', () => {
    expect(totals(p, 'league')).toEqual({ current: 10, planned: 30, unknown: 1, gaps: 1, bonus: 99 });
    expect(totals(p, 'empire')).toMatchObject({ current: 40, planned: 40 });
  });

  it('formate les durées', () => {
    expect(formatSeconds(42)).toBe('42 s');
    expect(formatSeconds(125)).toBe('2 min 05 s');
    expect(formatSeconds(5400)).toBe('1 h 30 min');
  });
});

describe('modifications', () => {
  const p = plan([entry('a1'), entry('a2'), entry('a3'), entry('b1', { chapter: 'b' })]);
  const ids = (q: FilmPlan) => q.entries.map(e => `${e.chapter}:${e.id}`);

  it('déplace avant une entrée, ou en fin de chapitre', () => {
    expect(ids(moveEntry(p, 'a3', { beforeId: 'a1', chapter: 'a' }))).toEqual(['a:a3', 'a:a1', 'a:a2', 'b:b1']);
    expect(ids(moveEntry(p, 'a1', { beforeId: 'b1', chapter: 'b' }))).toEqual(['a:a2', 'a:a3', 'b:a1', 'b:b1']);
    expect(ids(moveEntry(p, 'b1', { beforeId: null, chapter: 'a' }))).toEqual(['a:a1', 'a:a2', 'a:a3', 'a:b1']);
    expect(ids(moveEntry(p, 'a1', { beforeId: null, chapter: 'e' }))).toEqual(['a:a2', 'a:a3', 'b:b1', 'e:a1']);
    expect(moveEntry(p, 'zz', { beforeId: null, chapter: 'a' })).toBe(p);
    expect(moveEntry(p, 'a1', { beforeId: null, chapter: 'zz' })).toBe(p);
  });

  it('monte et descend parmi les entrées affichées', () => {
    const sib = p.entries.slice(0, 3);
    expect(ids(stepEntry(p, 'a2', sib, -1))).toEqual(['a:a2', 'a:a1', 'a:a3', 'b:b1']);
    expect(ids(stepEntry(p, 'a1', sib, 1))).toEqual(['a:a2', 'a:a1', 'a:a3', 'b:b1']);
    expect(ids(stepEntry(p, 'a2', sib, 1))).toEqual(['a:a1', 'a:a3', 'a:a2', 'b:b1']);
    expect(stepEntry(p, 'a1', sib, -1)).toBe(p);
    expect(stepEntry(p, 'a3', sib, 1)).toBe(p);
    // voisine filtrée : l'échange saute les entrées cachées
    expect(ids(stepEntry(p, 'a3', [p.entries[0], p.entries[2]], -1))).toEqual(['a:a3', 'a:a1', 'a:a2', 'b:b1']);
  });

  it('ajoute une entrée libre en fin de chapitre, avec un identifiant unique', () => {
    const q = addFreeEntry(addFreeEntry(p, 'a', { title: 'Scène à créer !', duration: 30, note: 'n' }), 'a', { title: 'Scène à créer !', duration: null, note: '' });
    expect(ids(q)).toEqual(['a:a1', 'a:a2', 'a:a3', 'a:free-scene-a-creer', 'a:free-scene-a-creer-2', 'b:b1']);
    const added = q.entries.find(e => e.id === 'free-scene-a-creer')!;
    expect(added).toMatchObject({ kind: 'free', status: 'todo', duration: 30, note: 'n', faction: 'common' });
    expect(validatePlan(q)).toEqual([]);
    expect(addFreeEntry(p, 'a', { title: '  ', duration: null, note: '' })).toBe(p);
  });

  it('modifie une entrée et sérialise sans les champs vidés', () => {
    const q = updateEntry(p, 'a1', { status: 'todo', note: undefined });
    expect(q.entries[0].status).toBe('todo');
    expect(serializePlan(q)).not.toMatch(/"note"/);
  });

  it('lie le chapitre du site', () => {
    expect(siteLink(entry('x', { siteChapter: 'ferris-locus' }), 'empire')).toBe('/cinematics?faction=empire&chapter=ferris-locus');
    expect(siteLink(entry('x', { siteChapter: 'ferris-locus' }), 'all')).toBe('/cinematics?faction=league&chapter=ferris-locus');
    expect(siteLink(entry('x', { siteChapter: 'empire-intro', faction: 'empire' }), 'league')).toBe('/cinematics?faction=empire&chapter=empire-intro');
    expect(siteLink(entry('x'), 'league')).toBeNull();
  });
});
