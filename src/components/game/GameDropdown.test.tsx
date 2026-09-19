import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { GameDropdown } from './GameDropdown';

const OPTIONS = [
  { value: 'all', label: 'Tout' },
  { value: 'completed', label: 'Terminé' },
  { value: 'inProgress', label: 'Pas terminé' },
] as const;

function setup(onChange = vi.fn()) {
  const utils = render(
    <GameDropdown value="all" options={[...OPTIONS]} onChange={onChange} label="Filtre" />,
  );
  return { ...utils, onChange, combobox: utils.getByRole('combobox') };
}

describe('GameDropdown', () => {
  it('reste fermé tant qu\'on ne clique pas sur le champ', () => {
    const { queryByRole, combobox } = setup();
    expect(combobox.getAttribute('aria-expanded')).toBe('false');
    expect(queryByRole('listbox')).toBeNull();
    expect(combobox.textContent).toBe('Tout');
  });

  it('ouvre la liste au clic et affiche les trois options du jeu', () => {
    const { combobox, getByRole, getAllByRole } = setup();
    fireEvent.click(combobox);
    expect(combobox.getAttribute('aria-expanded')).toBe('true');
    expect(getByRole('listbox')).toBeTruthy();
    expect(getAllByRole('option').map(o => o.textContent)).toEqual(['Tout', 'Terminé', 'Pas terminé']);
    expect(getAllByRole('option')[0].getAttribute('aria-selected')).toBe('true');
  });

  it('remonte la valeur choisie et se referme', () => {
    const { combobox, getByRole, queryByRole, onChange } = setup();
    fireEvent.click(combobox);
    fireEvent.click(getByRole('option', { name: 'Pas terminé' }));
    expect(onChange).toHaveBeenCalledWith('inProgress');
    expect(queryByRole('listbox')).toBeNull();
  });

  it('rend le focus au champ après une sélection', () => {
    const { combobox, getByRole } = setup();
    combobox.focus();
    fireEvent.click(combobox);
    fireEvent.click(getByRole('option', { name: 'Pas terminé' }));
    expect(document.activeElement).toBe(combobox);
  });

  it('rend le focus au champ après Échap', () => {
    const { combobox } = setup();
    combobox.focus();
    fireEvent.click(combobox);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(document.activeElement).toBe(combobox);
  });

  it('se ferme sur Échap', () => {
    const { combobox, queryByRole } = setup();
    fireEvent.click(combobox);
    expect(queryByRole('listbox')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(queryByRole('listbox')).toBeNull();
  });

  it('se ferme au clic à l\'extérieur', () => {
    const { combobox, queryByRole } = setup();
    fireEvent.click(combobox);
    expect(queryByRole('listbox')).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(queryByRole('listbox')).toBeNull();
  });
});
