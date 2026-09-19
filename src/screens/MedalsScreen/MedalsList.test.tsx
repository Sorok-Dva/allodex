import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import type { Medal } from '@/data/medals.types';
import { MedalsList } from './MedalsList';
import type { MedalsState } from './useMedalsState';

const medal = (over: Partial<Medal>): Medal => ({
  id: 'x', name: 'Nom', description: 'Desc', icon: 'i',
  categoryIndex: 0, subCategoryIndex: 0,
  ranks: [{ completeProgress: 1, name: 'r', description: 'Desc', score: 10 }],
  currentRank: 0, ...over,
});

function state(visible: Medal[]): MedalsState {
  return {
    selected: { categoryIndex: 0, subCategoryIndex: 0 },
    select: vi.fn(), openCategory: 0, toggleCategory: vi.fn(),
    query: '', setQuery: vi.fn(),
    filter: 'completed', setFilter: vi.fn(),
    tracked: new Map<string, boolean>(), setTracked: vi.fn(),
    visible, title: 'Astral ouvert',
  };
}

describe('MedalsList', () => {
  it('affiche « Aucun succès. » quand le filtre ne laisse rien', () => {
    const { getByText, queryAllByRole } = render(<MedalsList state={state([])} />);
    expect(getByText('Aucun succès.')).toBeTruthy();
    expect(queryAllByRole('article')).toHaveLength(0);
  });

  it('affiche les entrées et pas le message vide dès qu\'il y a un succès', () => {
    const { queryByText, getByText } = render(
      <MedalsList state={state([medal({ id: 'a', name: 'Connecté avec les étoiles' })])} />,
    );
    expect(queryByText('Aucun succès.')).toBeNull();
    expect(getByText('Connecté avec les étoiles')).toBeTruthy();
  });

  it('rend le titre de la sous-catégorie et le menu de filtre', () => {
    const { getByRole } = render(<MedalsList state={state([])} />);
    expect(getByRole('heading', { level: 2 }).textContent).toBe('Astral ouvert');
    expect(getByRole('combobox').textContent).toBe('Terminé');
  });
});
