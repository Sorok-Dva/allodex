// @vitest-environment node
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createServer, type Server } from 'node:http';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { handlePlanRequest, revisionOf } from './filmPlanPlugin.ts';
import { serializePlan, type FilmPlan } from '../../src/screens/FilmPlanScreen/filmPlan.ts';

const PLAN: FilmPlan = {
  format: 1, targetMinutes: 90,
  chapters: [{ id: 'a', title: 'A', version: '1.0', faction: 'common' }],
  entries: [{ id: 'x', title: 'X', chapter: 'a', faction: 'common', zone: '', version: '1.0', kind: 'video', duration: 3, status: 'film', priority: 'none' }],
};

let dir = '';
let file = '';
let server: Server;
let base = '';
const writes: string[] = [];

beforeAll(async () => {
  dir = mkdtempSync(path.join(tmpdir(), 'film-plan-'));
  file = path.join(dir, 'film_plan.json');
  server = createServer((req, res) => { void handlePlanRequest(file, req, res, rev => writes.push(rev)); });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  base = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`;
});
afterAll(() => { server.close(); rmSync(dir, { recursive: true, force: true }); });
beforeEach(() => { writeFileSync(file, serializePlan(PLAN)); writes.length = 0; });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const json = async (res: Response): Promise<any> => res.json();
const put = (body: unknown) => fetch(base, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

describe('greffon du plan du film', () => {
  it('sert le plan et sa révision', async () => {
    const res = await fetch(base);
    expect(res.status).toBe(200);
    const body = await json(res);
    expect(body.plan).toEqual(PLAN);
    expect(body.revision).toBe(revisionOf(serializePlan(PLAN)));
    expect(body.errors).toEqual([]);
  });

  it('enregistre un plan valide de façon atomique', async () => {
    const { revision } = await json(await fetch(base));
    const next = { ...PLAN, entries: [{ ...PLAN.entries[0], status: 'todo' }] };
    const res = await put({ baseRevision: revision, plan: next });
    expect(res.status).toBe(200);
    const text = readFileSync(file, 'utf8');
    expect(JSON.parse(text).entries[0].status).toBe('todo');
    expect((await json(res)).revision).toBe(revisionOf(text));
    expect(writes).toEqual([revisionOf(text)]);
    expect(readdirSync(dir)).toEqual(['film_plan.json']);   // pas de fichier temporaire laissé
  });

  it('refuse un plan invalide sans toucher au fichier', async () => {
    const { revision } = await json(await fetch(base));
    const res = await put({ baseRevision: revision, plan: { ...PLAN, entries: [{ ...PLAN.entries[0], chapter: 'zz' }] } });
    expect(res.status).toBe(422);
    expect((await json(res)).errors.join()).toMatch(/chapitre inconnu/);
    expect(readFileSync(file, 'utf8')).toBe(serializePlan(PLAN));
  });

  it('refuse d’écraser un fichier modifié sur disque depuis la lecture', async () => {
    const { revision } = await json(await fetch(base));
    const edited = serializePlan({ ...PLAN, targetMinutes: 100 });
    writeFileSync(file, edited);   // un agent édite le fichier
    const res = await put({ baseRevision: revision, plan: PLAN });
    expect(res.status).toBe(409);
    expect((await json(res)).revision).toBe(revisionOf(edited));
    expect(readFileSync(file, 'utf8')).toBe(edited);
  });

  it('refuse un corps illisible et les autres méthodes', async () => {
    expect((await fetch(base, { method: 'PUT', body: '{' })).status).toBe(400);
    expect((await fetch(base, { method: 'POST', body: '{}' })).status).toBe(405);
  });
});
