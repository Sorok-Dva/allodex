import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { OpeningScreen } from './OpeningScreen';
import { I18nProvider, LANG_KEY } from '@/lib/i18n';

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
  it('traduit le menu, conserve les paramètres URL et mémorise le choix de langue', () => {
    window.history.replaceState(null, '', '/?skipIntro&lang=fr#menu');
    const page = render(<I18nProvider><OpeningScreen /></I18nProvider>);
    fireEvent.click(page.getByRole('button', { name: 'English' }));
    expect(page.getByRole('button', { name: 'Achievements' })).toBeTruthy();
    expect(page.getByRole('button', { name: 'Chronicles' })).toBeTruthy();
    expect(page.getByRole('button', { name: 'Replay intro' })).toBeTruthy();
    expect(page.getByRole('link', { name: 'Terms of use' }).getAttribute('href')).toBe('/cgu');
    expect(page.getByRole('link', { name: 'Sorok-Dva' }).getAttribute('href')).toBe('https://p-42.fr/allodex-developer');
    expect(window.localStorage.getItem(LANG_KEY)).toBe('en');
    expect(document.documentElement.lang).toBe('en');
    expect(window.location.search).toBe('?skipIntro=&lang=en');
    expect(window.location.hash).toBe('#menu');
    fireEvent.click(page.getByRole('button', { name: 'Français' }));
    expect(page.getByRole('button', { name: 'Succès' })).toBeTruthy();
    expect(window.localStorage.getItem(LANG_KEY)).toBe('fr');
  });
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
