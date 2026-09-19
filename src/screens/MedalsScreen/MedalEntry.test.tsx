import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import type { Medal } from '@/data/medals.types';
import { MedalEntry } from './MedalEntry';

const base = (over: Partial<Medal> = {}): Medal => ({
  id: 'x',
  name: 'Connecté avec les étoiles',
  description: 'Connectez-vous depuis un allod astral.',
  icon: 'Interface/Icons/Misc/Event/GoldMedal',
  categoryIndex: 3,
  subCategoryIndex: 0,
  ranks: [{ completeProgress: 1, name: 'r', description: 'Connectez-vous depuis un allod astral.', score: 20 }],
  currentRank: 0,
  ...over,
});

/** Succès terminé, avec date, comme la première entrée de `refs/astral.png`. */
const done = (over: Partial<Medal> = {}) =>
  base({ currentRank: 1, finishDate: '2026-08-29T20:54', ...over });

const series = (count: number) =>
  Array.from({ length: count }, (_, i) => ({
    medalId: `m${i + 1}`,
    success: i === 0,
    icon: 'Interface/Icons/Misc/Event/GoldMedal',
    rank: i + 1,
  }));

describe('MedalEntry', () => {
  it('pose le parchemin doré sur un succès terminé', () => {
    const gold = render(<MedalEntry medal={done()} />).getByTestId('medal-paper');
    expect(gold.dataset.complete).toBe('true');
    expect(gold.style.backgroundImage).toContain('MedalPaperComplete.png');
  });

  it('pose le parchemin gris sur un succès en cours', () => {
    const grey = render(<MedalEntry medal={base()} />).getByTestId('medal-paper');
    expect(grey.dataset.complete).toBe('false');
    expect(grey.style.backgroundImage).toContain('MedalPaper.png');
    expect(grey.style.backgroundImage).not.toContain('Complete');
  });

  it('affiche la date quand le succès est terminé', () => {
    const { getByText, queryByRole } = render(<MedalEntry medal={done()} />);
    expect(getByText('29.08.2026')).toBeTruthy();
    expect(queryByRole('checkbox')).toBeNull();
  });

  it('affiche la case de suivi quand le succès n\'est pas terminé', () => {
    const { getByRole, queryByText } = render(<MedalEntry medal={base()} />);
    expect(getByRole('checkbox').getAttribute('aria-checked')).toBe('false');
    expect(queryByText('29.08.2026')).toBeNull();
  });

  it('remonte le suivi du succès au clic sur la case', () => {
    const onTrack = vi.fn();
    const { getByRole } = render(<MedalEntry medal={base({ id: 'parfait-astral' })} onTrack={onTrack} />);
    fireEvent.click(getByRole('checkbox'));
    expect(onTrack).toHaveBeenCalledWith('parfait-astral', true);
  });

  it('numérote la série de succès en chiffres romains I à VI', () => {
    const { getByText, getByTestId } = render(<MedalEntry medal={base({ medalCollection: series(6) })} />);
    expect(getByText('Série de succès :')).toBeTruthy();
    const slots = within(getByTestId('medal-series')).getAllByRole('listitem');
    expect(slots.map(li => li.querySelector('span')?.textContent)).toEqual(['I', 'II', 'III', 'IV', 'V', 'VI']);
  });

  it('affiche l\'infobulle du jeu au survol du nom', () => {
    const medal = done();
    const { getByRole, queryByText, getAllByText, getByText } = render(<MedalEntry medal={medal} />);
    expect(queryByText('Shift + clic : Lien vers les succès')).toBeNull();

    fireEvent.mouseEnter(getByRole('heading', { level: 3 }));

    // Le nom apparaît alors deux fois : dans l'entrée et en titre de l'infobulle.
    expect(getAllByText(medal.name)).toHaveLength(2);
    expect(getByText('Date : 20:54 29.08.2026')).toBeTruthy();
    expect(getByText('Shift + clic : Lien vers les succès')).toBeTruthy();
  });

  // Spec § 7.3 : les deux blocs sont indépendants. Aucun succès du mock ne porte les
  // deux, d'où ce succès de test.
  it('affiche ensemble la barre et la série quand le succès porte les deux', () => {
    const both = base({
      ranks: [{ completeProgress: 10, name: 'r', description: 'd', score: 20 }],
      progress: { value: 4 },
      medalCollection: series(3),
    });
    const { getByText, getByTestId, container } = render(<MedalEntry medal={both} />);
    expect(getByText('4 sur 10')).toBeTruthy();
    expect(getByText('Série de succès :')).toBeTruthy();
    expect(within(getByTestId('medal-series')).getAllByRole('listitem')).toHaveLength(3);
    // 84 (parchemin nu) + 21,5 (bloc barre) + 75 (bloc série) ; la série est décalée
    // vers le bas de la hauteur du bloc barre.
    const entry = container.querySelector('article') as HTMLElement;
    expect(entry.style.height).toBe('180.5px');
    expect(entry.style.getPropertyValue('--series-shift')).toBe('21.5px');
  });

  it('ne décale pas la série quand il n\'y a pas de barre', () => {
    const { container } = render(<MedalEntry medal={base({ medalCollection: series(6) })} />);
    const entry = container.querySelector('article') as HTMLElement;
    expect(entry.style.height).toBe('159px');
    expect(entry.style.getPropertyValue('--series-shift')).toBe('0px');
  });
});
