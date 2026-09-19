import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import { MedalsNavigation } from './MedalsNavigation';
import { useMedalsState } from './useMedalsState';

const EMPTY_DATASET: MedalsDataset = { categories: [], medals: [], totalScore: 0 };
const DATASET = parseDataset(mock);

function Harness({ ds }: { ds: MedalsDataset }) {
  const state = useMedalsState(ds);
  return <MedalsNavigation ds={ds} state={state} />;
}

/** Pilule d'une catégorie, repérée par son libellé. */
const pill = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name}$`) });

/** Éléments de la liste des catégories (la sous-liste dépliée est imbriquée plus bas). */
const categories = (container: HTMLElement) => Array.from(container.querySelector('ul')!.children);

describe('MedalsNavigation', () => {
  it('ne plante pas avec zéro catégorie et affiche une liste vide', () => {
    const { container } = render(<Harness ds={EMPTY_DATASET} />);
    const list = container.querySelector('ul');
    expect(list).not.toBeNull();
    expect(list?.children.length).toBe(0);
    expect(screen.getByPlaceholderText('Recherche de succès...')).toBeDefined();
  });

  it('affiche les 17 catégories du jeu en pilules', () => {
    const { container } = render(<Harness ds={DATASET} />);
    expect(categories(container)).toHaveLength(17);
    expect(pill('Progression')).toBeTruthy();
    expect(pill('Forteresse de guilde')).toBeTruthy();
  });

  it('prive « Progression » de médaillon et de dépliage', () => {
    render(<Harness ds={DATASET} />);
    const progression = pill('Progression');
    // Ni médaillon +/− ni état déplié : c'est une vue, pas une catégorie (spec § 7.2).
    expect(progression.querySelector('span[class*="medallion"]')).toBeNull();
    expect(progression.getAttribute('aria-expanded')).toBeNull();
    expect(progression.getAttribute('aria-disabled')).toBe('true');

    // Astral est dépliée au chargement ; cliquer « Progression » n'y change rien.
    expect(pill('Astral').getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(progression);
    expect(pill('Astral').getAttribute('aria-expanded')).toBe('true');
    expect(progression.getAttribute('aria-expanded')).toBeNull();
  });

  it('les autres catégories portent un médaillon', () => {
    render(<Harness ds={DATASET} />);
    expect(pill('Personnage').querySelector('span[class*="medallion"]')).not.toBeNull();
  });

  it('ne garde qu\'une seule catégorie dépliée à la fois', () => {
    render(<Harness ds={DATASET} />);
    expect(pill('Astral').getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(pill('Personnage'));

    expect(pill('Personnage').getAttribute('aria-expanded')).toBe('true');
    expect(pill('Astral').getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('button', { name: /^Astral ouvert/ })).toBeNull();
  });

  it('affiche « Nom - terminés/total » sur les sous-catégories dépliées', () => {
    const { container } = render(<Harness ds={DATASET} />);
    const astral = categories(container)[3] as HTMLElement;
    const rows = within(astral).getAllByRole('button').slice(1);
    expect(rows.map(r => r.textContent)).toEqual(['Astral ouvert - 5/29', 'Allods Astraux - 15/15']);
  });
});
