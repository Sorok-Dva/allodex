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

  it("n'affiche pas la note technique du thème", () => {
    const entry = { ...ENTRY, theme_note: 'thème du client 15.0 (approximation)' };
    const { queryByText } = render(<ThemePlayer entry={entry} playing={false} onToggle={vi.fn()} />);
    expect(queryByText('thème du client 15.0 (approximation)')).toBeNull();
  });

  it('signale un thème non extrait, sans bouton de lecture', () => {
    const { theme: _theme, ...entry } = ENTRY;
    const { getByText, queryByLabelText } = render(<ThemePlayer entry={entry} playing={false} onToggle={vi.fn()} />);
    expect(getByText('Thème non extrait')).toBeTruthy();
    expect(queryByLabelText('Lire le thème')).toBeNull();
  });

  it('signale un thème indisponible et grise le bouton (aucun client ne le conserve)', () => {
    const { theme: _theme, ...rest } = ENTRY;
    const entry = { ...rest, theme_note: 'Thème non disponible dans les clients archivés' };
    const { getByText, getByLabelText, queryByLabelText, queryByText } = render(
      <ThemePlayer entry={entry} playing={false} onToggle={vi.fn()} />,
    );
    expect(getByText('Thème non disponible')).toBeTruthy();
    expect(queryByText('Thème non disponible dans les clients archivés')).toBeNull();
    expect((getByLabelText('Thème indisponible') as HTMLButtonElement).disabled).toBe(true);
    expect(queryByLabelText('Lire le thème')).toBeNull();
  });
});
