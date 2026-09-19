import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import type { ArchiveEntry } from '@/lib/assets';
import { ThemePlayer, formatDuration } from './ThemePlayer';

const ENTRY: ArchiveEntry = {
  version: '8.0',
  label: 'Allods Online 8.0',
  media: 'image',
  background: 'background.png',
  theme: { name: 'MainMenu_Immortality', duration: 182.687, ogg: 'theme.ogg', mp3: 'theme.mp3' },
};

describe('formatDuration', () => {
  it('formate en m:ss', () => {
    expect(formatDuration(182.687)).toBe('3:02');
    expect(formatDuration(168.046)).toBe('2:48');
    expect(formatDuration(9.977)).toBe('0:09');
  });
});

describe('ThemePlayer', () => {
  it('affiche le nom du thème et sa durée', () => {
    const { getByText, getByTestId } = render(<ThemePlayer entry={ENTRY} playing={false} onToggle={vi.fn()} />);
    expect(getByText('MainMenu_Immortality')).toBeTruthy();
    // Le deux-points est un élément à part (lisibilité) : on lit le texte complet.
    expect(getByTestId('theme-duration').textContent).toBe('3:02');
  });

  it('bascule lecture/pause par le bouton', () => {
    const onToggle = vi.fn();
    const { getByLabelText, rerender } = render(<ThemePlayer entry={ENTRY} playing={false} onToggle={onToggle} />);
    fireEvent.click(getByLabelText('Lire le thème'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    rerender(<ThemePlayer entry={ENTRY} playing onToggle={onToggle} />);
    expect(getByLabelText('Mettre le thème en pause')).toBeTruthy();
  });

  it('affiche la note du thème quand elle existe', () => {
    const entry = { ...ENTRY, theme_note: 'thème du client 15.0 (approximation)' };
    const { getByText } = render(<ThemePlayer entry={entry} playing={false} onToggle={vi.fn()} />);
    expect(getByText('thème du client 15.0 (approximation)')).toBeTruthy();
  });

  it('signale un thème non extrait, sans bouton de lecture', () => {
    const { theme: _theme, ...entry } = ENTRY;
    const { getByText, queryByLabelText } = render(<ThemePlayer entry={entry} playing={false} onToggle={vi.fn()} />);
    expect(getByText('Thème non extrait')).toBeTruthy();
    expect(queryByLabelText('Lire le thème')).toBeNull();
  });
});
