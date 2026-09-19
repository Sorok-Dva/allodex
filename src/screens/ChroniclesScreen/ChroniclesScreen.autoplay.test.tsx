import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { AudioProvider } from '@/lib/audio/AudioProvider';
import type { ArchiveEntry } from '@/lib/assets';
import { ChroniclesScreen } from './ChroniclesScreen';

/**
 * Ici le **vrai** moteur audio est monté : c'est l'état de lecture rapporté par les
 * éléments `<audio>` qui doit piloter le bouton du lecteur, pas l'intention de la page.
 * Sans geste utilisateur, la politique d'autoplay interdit `play()` — le bouton doit
 * donc proposer « Lire le thème », et le clic (qui est le geste) démarrer la lecture.
 */
const ENTRIES: ArchiveEntry[] = [
  {
    version: '8.0', label: 'Allods Online 8.0', media: 'image', background: 'background.png',
    theme: { name: 'MainMenu_Immortality', duration: 182.687, ogg: 'theme.ogg', mp3: 'theme.mp3' },
  },
];

vi.mock('@/lib/assets', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/assets')>();
  return { ...actual, archiveEntries: () => ENTRIES };
});

beforeEach(() => {
  window.localStorage.clear();
  window.history.pushState(null, '', '/chroniques?v=8.0');
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
});

const setup = () => render(<AudioProvider><ChroniclesScreen /></AudioProvider>);

describe('ChroniclesScreen — lecture réelle du thème', () => {
  it('sans geste utilisateur : le bouton propose « Lire le thème » et rien ne joue', () => {
    const { getByLabelText, queryByLabelText } = setup();
    expect(getByLabelText('Lire le thème')).toBeTruthy();
    expect(queryByLabelText('Mettre le thème en pause')).toBeNull();
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('après un geste, le clic lance la lecture et le bouton bascule sur l\'événement `play`', () => {
    const { getByLabelText, getByTestId } = setup();
    act(() => { window.dispatchEvent(new Event('pointerdown')); });

    fireEvent.click(getByLabelText('Lire le thème'));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();

    // Le bouton ne bascule que sur l'événement du média, pas sur l'appel à `play()`.
    const el = getByTestId('music-a') as HTMLAudioElement;
    act(() => { el.dispatchEvent(new Event('play')); });
    expect(getByLabelText('Mettre le thème en pause')).toBeTruthy();

    act(() => { el.dispatchEvent(new Event('pause')); });
    expect(getByLabelText('Lire le thème')).toBeTruthy();
  });
});
