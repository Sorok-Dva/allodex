import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { OpeningScreen } from './OpeningScreen';

const setTrack = vi.fn();
const playSfx = vi.fn();
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({ muted: false, track: null, ready: true, toggleMuted: vi.fn(), setTrack, playSfx }),
}));

beforeEach(() => {
  setTrack.mockClear();
  playSfx.mockClear();
  window.localStorage.clear();
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
});

// `?skipIntro` place l'écran directement en phase « menu » (voir `useIntroState`).
function renderMenu() {
  window.history.pushState(null, '', '/?skipIntro');
  return render(<OpeningScreen />);
}

describe('OpeningScreen — audio', () => {
  it('demande la piste menu au montage (menu ou intro)', () => {
    renderMenu();
    expect(setTrack).toHaveBeenCalledWith('menu');
  });

  it('passe à ambient et joue ui-click au premier clic sur un item de la barre', () => {
    const { getByRole } = renderMenu();
    fireEvent.click(getByRole('button', { name: 'Succès' }));
    expect(setTrack).toHaveBeenCalledWith('ambient');
    expect(playSfx).toHaveBeenCalledWith('ui-click');
  });

  it('ne redéclenche pas ambient/ui-click sur les clics suivants', () => {
    const { getByRole } = renderMenu();
    fireEvent.click(getByRole('button', { name: 'Succès' }));
    setTrack.mockClear();
    playSfx.mockClear();
    fireEvent.click(getByRole('button', { name: 'Personnage' }));
    expect(setTrack).not.toHaveBeenCalled();
    expect(playSfx).not.toHaveBeenCalled();
  });
});
