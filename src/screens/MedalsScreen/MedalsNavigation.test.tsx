import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MedalsDataset } from '@/data/medals.types';
import { MedalsNavigation } from './MedalsNavigation';
import { useMedalsState } from './useMedalsState';

const EMPTY_DATASET: MedalsDataset = { categories: [], medals: [], totalScore: 0 };

function Harness({ ds }: { ds: MedalsDataset }) {
  const state = useMedalsState(ds);
  return <MedalsNavigation ds={ds} state={state} />;
}

describe('MedalsNavigation', () => {
  it('ne plante pas avec zéro catégorie et affiche une liste vide', () => {
    const { container } = render(<Harness ds={EMPTY_DATASET} />);
    const list = container.querySelector('ul');
    expect(list).not.toBeNull();
    expect(list?.children.length).toBe(0);
    expect(screen.getByPlaceholderText('Recherche de succès...')).toBeDefined();
  });
});
