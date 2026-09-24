// @vitest-environment node
// Le plan du dépôt (`tools/film_plan.json`), tel qu'un agent ou la page l'a laissé.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { serializePlan, validatePlan, type FilmPlan } from '../../src/screens/FilmPlanScreen/filmPlan.ts';

const ROOT = path.resolve(import.meta.dirname, '../..');

describe('tools/film_plan.json', () => {
  const text = readFileSync(path.join(ROOT, 'tools/film_plan.json'), 'utf8');
  const data = JSON.parse(text) as FilmPlan;
  const index = JSON.parse(readFileSync(path.join(ROOT, 'public/game/cinematics/cinematics.json'), 'utf8')) as { cinematics: { id: string }[] };

  it('est un plan valide, écrit comme la page l’écrit', () => {
    expect(validatePlan(data)).toEqual([]);
    expect(serializePlan(data)).toBe(text);
  });

  it('reprend chaque chapitre publié du film, et seulement des chapitres existants', () => {
    const published = new Set(index.cinematics.map(c => c.id));
    const linked = new Set(data.entries.map(e => e.siteChapter).filter(Boolean));
    for (const id of published) expect(linked, id).toContain(id);
    for (const id of linked) expect(published, String(id)).toContain(id);
  });

  it('cite une source pour chaque entrée de l’inventaire', () => {
    for (const e of data.entries) if (e.kind !== 'free') expect(e.source?.length ?? 0, e.id).toBeGreaterThan(10);
  });
});
