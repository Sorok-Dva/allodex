import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { FilmPlan } from './filmPlan';
import type { PlanApi, SaveResult } from './planApi';

let search = 'faction=league';
vi.mock('@/lib/router', () => ({
  navigate: vi.fn(),
  useRoute: () => ({ path: '/dev/film', query: new URLSearchParams(search) }),
}));
import FilmPlanScreen from './FilmPlanScreen';

const PLAN: FilmPlan = {
  format: 1, targetMinutes: 90,
  chapters: [
    { id: 'start', title: 'Zone de départ', version: '4.0', faction: 'league' },
    { id: 'kania', title: 'Kania', version: '1.0', faction: 'league', summary: 'Quêtes de Kania.' },
    { id: 'ferris', title: 'Ferris', version: '6.0', faction: 'common' },
    { id: 'hadagan', title: 'Xadagan', version: '1.0', faction: 'empire' },
  ],
  entries: [
    { id: 'klement', title: 'La mort du Grand Mage', chapter: 'start', faction: 'league', zone: 'Inst_LeagueStart', version: '7.0', kind: 'engine', duration: 53, status: 'pending', priority: 'high', priorityProposed: true },
    { id: 'locus', title: 'Le Locus', chapter: 'ferris', faction: 'common', zone: 'FerrisRaid', version: '6.0', kind: 'engine', duration: 162, status: 'film', priority: 'none', siteChapter: 'ferris-locus' },
    { id: 'capsule', title: 'La capsule', chapter: 'ferris', faction: 'common', zone: 'Ferris_indoor', version: '6.0', kind: 'engine', duration: 47, durationEstimated: true, status: 'todo', priority: 'high', source: 'Arbre 7.0 : Ferris_3_4_2' },
    { id: 'igsh', title: 'Igsh', chapter: 'hadagan', faction: 'empire', zone: 'Hadagan', version: '1.0', kind: 'engine', duration: null, status: 'discarded', priority: 'none' },
  ],
};

function fakeApi(plan = PLAN) {
  let listener: ((rev: string) => void) | null = null;
  const saves: { plan: FilmPlan; base: string }[] = [];
  let revision = 1;
  const api: PlanApi & { saves: typeof saves; emit: (rev: string) => void; next: SaveResult | null } = {
    saves, next: null,
    load: vi.fn(async () => ({ plan: structuredClone(plan), revision: `r${revision}`, errors: [] })),
    save: vi.fn(async (p: FilmPlan, base: string) => {
      saves.push({ plan: p, base });
      if (api.next) { const r = api.next; api.next = null; return r; }
      revision += 1;
      return { ok: true as const, revision: `r${revision}` };
    }),
    subscribe: fn => { listener = fn; return () => { listener = null; }; },
    emit: rev => listener?.(rev),
  };
  return api;
}

beforeEach(() => { search = 'faction=league'; });
afterEach(() => { cleanup(); vi.useRealTimers(); });

const rowOf = (id: string) => screen.getByTestId(`entry-${id}`);

describe('FilmPlanScreen', () => {
  it('montre la frise de la faction, les trous et les totaux', async () => {
    render(<FilmPlanScreen api={fakeApi()} />);
    await screen.findByTestId('chapter-ferris');
    expect(screen.queryByTestId('chapter-hadagan')).toBeNull();          // chapitre de l'Empire
    expect(screen.getByTestId('chapter-start').dataset.gap).toBe('partial');
    expect(screen.getByTestId('chapter-kania').dataset.gap).toBe('empty');
    expect(screen.getByTestId('chapter-ferris').dataset.gap).toBe('none');
    expect(within(screen.getByTestId('chapter-kania')).getByText('Trou : aucune scène connue')).toBeTruthy();
    const totals = screen.getByTestId('totals');
    expect(totals.textContent).toContain('2 min 42 s');                  // film actuel : le Locus
    expect(totals.textContent).toContain('4 min 22 s');                  // visé : + capsule + Klement
    expect(totals.textContent).toContain('1 h 30 min');
    expect(within(rowOf('locus')).getByText('Voir').getAttribute('href')).toBe('/cinematics?faction=league&chapter=ferris-locus');
    expect(within(rowOf('klement')).getByText('proposée')).toBeTruthy();
  });

  it('filtre par statut et par texte', async () => {
    render(<FilmPlanScreen api={fakeApi()} />);
    await screen.findByTestId('entry-locus');
    fireEvent.click(screen.getByTestId('filter-film'));
    expect(screen.queryByTestId('entry-locus')).toBeNull();
    expect(screen.getByTestId('entry-capsule')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Rechercher'), { target: { value: 'ferris_3_4' } });
    expect(screen.getByTestId('entry-capsule')).toBeTruthy();
    expect(screen.queryByTestId('entry-klement')).toBeNull();
    fireEvent.click(screen.getByTestId('filter-gaps'));
    expect(screen.queryByTestId('chapter-ferris')).toBeNull();
  });

  it('enregistre un changement de statut et un réordonnancement', async () => {
    const api = fakeApi();
    render(<FilmPlanScreen api={api} />);
    await screen.findByTestId('entry-capsule');
    vi.useFakeTimers();
    fireEvent.click(within(rowOf('capsule')).getByLabelText('Statut de « La capsule »'));
    fireEvent.click(within(rowOf('capsule')).getByRole('option', { name: 'En attente' }));
    fireEvent.click(within(rowOf('capsule')).getByLabelText('Monter « La capsule »'));
    expect(screen.getByTestId('save-state').textContent).toBe('Modifications en attente');
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(api.saves).toHaveLength(1);                                    // une seule écriture, différée
    const saved = api.saves[0];
    expect(saved.base).toBe('r1');
    expect(saved.plan.entries.map(e => e.id)).toEqual(['klement', 'capsule', 'locus', 'igsh']);
    expect(saved.plan.entries.find(e => e.id === 'capsule')?.status).toBe('pending');
    expect(screen.getByTestId('save-state').textContent).toContain('Enregistré');
  });

  it('ajoute une entrée libre par la fenêtre du jeu', async () => {
    const api = fakeApi();
    render(<FilmPlanScreen api={api} />);
    await screen.findByTestId('chapter-kania');
    fireEvent.click(screen.getByTestId('add-kania'));
    fireEvent.change(screen.getByTestId('add-title'), { target: { value: 'Fin du chapitre 1' } });
    fireEvent.change(screen.getByTestId('add-duration'), { target: { value: '45' } });
    fireEvent.click(screen.getByTestId('add-submit'));
    const row = await screen.findByTestId('entry-free-fin-du-chapitre-1');
    expect(row.textContent).toContain('≈ 45 s');
    expect(screen.getByTestId('chapter-kania').dataset.gap).toBe('partial');
    await waitFor(() => expect(api.saves).toHaveLength(1), { timeout: 2000 });
    expect(api.saves[0].plan.entries.find(e => e.id === 'free-fin-du-chapitre-1')).toMatchObject({ chapter: 'kania', kind: 'free', status: 'todo', faction: 'league' });
  });

  it('se recharge quand le fichier change sur disque, et signale un conflit', async () => {
    const api = fakeApi();
    render(<FilmPlanScreen api={api} />);
    await screen.findByTestId('entry-capsule');
    act(() => api.emit('r1'));                                            // notre propre révision : rien
    expect(api.load).toHaveBeenCalledTimes(1);
    act(() => api.emit('r9'));
    await waitFor(() => expect(api.load).toHaveBeenCalledTimes(2));
    // modification locale en attente + changement sur disque : conflit, pas de rechargement
    fireEvent.click(within(rowOf('capsule')).getByLabelText('Monter « La capsule »'));
    act(() => api.emit('r10'));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(api.load).toHaveBeenCalledTimes(2);
    api.next = { ok: false, conflict: true, revision: 'r10' };
    fireEvent.click(screen.getByText('Recharger le fichier (perdre mes modifications)'));
    await waitFor(() => expect(api.load).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });
});
