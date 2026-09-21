import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { GameActionBar, type ActionItem } from './GameActionBar';

const ITEMS: ActionItem[] = [
  { id: 'medals', base: 'Interface/Ingame/ContextPinMenu3/textures/ButtonMedals', label: 'Succès' },
];

describe('GameActionBar', () => {
  it('garde l\'icône Normal visible et révèle le halo Highlight au survol', () => {
    const { getByRole, getByTestId } = render(<GameActionBar items={ITEMS} />);
    const button = getByRole('button', { name: 'Succès' });
    const base = getByTestId('action-base-medals') as HTMLElement;
    const highlight = getByTestId('action-highlight-medals') as HTMLElement;

    // Avant survol : la couche Normal est en place, le halo est présent mais invisible.
    expect(base.style.backgroundImage).toContain('ButtonMedalsNormal.png');
    expect(highlight.style.backgroundImage).toContain('ButtonMedalsHighlight.png');
    expect(highlight.style.opacity).toBe('0');

    fireEvent.mouseEnter(button);

    // Au survol : l'icône Normal reste affichée, seul le halo Highlight devient visible.
    expect(base.style.backgroundImage).toContain('ButtonMedalsNormal.png');
    expect(highlight.style.opacity).toBe('1');

    fireEvent.mouseLeave(button);

    expect(highlight.style.opacity).toBe('0');
  });
});
