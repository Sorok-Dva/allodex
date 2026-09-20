import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { OpeningScreen } from './OpeningScreen';
import { I18nProvider, LANG_KEY } from '@/lib/i18n';
import { resetIntroMemory, FADE_MS, INTRO_MS } from './useIntroState';

const setTrack = vi.fn();
const playSfx = vi.fn();
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({ muted: false, track: null, ready: true, toggleMuted: vi.fn(), setTrack, playSfx }),
}));

beforeEach(() => {
  setTrack.mockClear();
  playSfx.mockClear();
  window.localStorage.clear();
  resetIntroMemory();
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
    expect(page.getByRole('link', { name: 'Terms of use' }).getAttribute('href')).toBe('/terms');
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

  it("affiche l'image de fond si la dernière version du jeu est de type image", async () => {
    const assets = await import('@/lib/assets');
    vi.spyOn(assets, 'latestArchiveEntry').mockReturnValue({
      version: '8.0',
      label: '8.0',
      media: 'image',
      background: 'background.png',
    });
    const { container } = renderMenu();
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('/game/archive/8.0/background.png');
    vi.restoreAllMocks();
  });

  it("masque le bouton Replay intro et passe directement au menu si la dernière version n'a pas d'intro", async () => {
    const assets = await import('@/lib/assets');
    vi.spyOn(assets, 'latestArchiveEntry').mockReturnValue({
      version: '1.0',
      label: '1.0',
      media: 'image',
      background: 'background.png',
    });
    window.history.pushState(null, '', '/');
    const { queryByRole } = render(<OpeningScreen />);
    expect(queryByRole('button', { name: "Rejouer l'intro" })).toBeNull();
    vi.restoreAllMocks();
  });

  it("affiche le logo Allodex sur l'écran d'accueil", () => {
    const { getByTestId } = renderMenu();
    const logo = getByTestId('game-logo');
    expect(logo.getAttribute('src')).toBe('/logo.png');
    expect(logo.getAttribute('alt')).toBe('Allodex');
  });
});

describe('OpeningScreen — intro', () => {
  beforeEach(() => { vi.useFakeTimers(); window.history.pushState(null, '', '/'); });
  afterEach(() => vi.useRealTimers());

  it("joue l'intro à chaque chargement de page, avec le logo animé par-dessus la vidéo", () => {
    const { container, getByTestId, queryByRole } = render(<OpeningScreen />);
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('intro');
    const intro = getByTestId('intro-video');
    expect(intro.querySelector('source')?.getAttribute('src')).toContain('intro.webm');
    expect(getByTestId('game-logo')).toBeTruthy();
    expect(queryByRole('button', { name: 'Succès' })).toBeNull();
  });

  it('fond l’intro sur le menu : la vidéo reste montée pendant le fondu puis disparaît', () => {
    const { container, getByTestId, queryByTestId, getByRole } = render(<OpeningScreen />);
    const intro = getByTestId('intro-video');
    act(() => { vi.advanceTimersByTime(INTRO_MS); });
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('fading');
    expect(getByTestId('intro-video')).toBe(intro);     // même élément : pas de redémarrage
    expect(getByRole('button', { name: 'Succès' })).toBeTruthy(); // menu déjà monté dessous
    act(() => { vi.advanceTimersByTime(FADE_MS); });
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('menu');
    expect(queryByTestId('intro-video')).toBeNull();
  });

  it('un clic ou Espace passe l’intro (fondu immédiat), et « Rejouer » la relance', () => {
    const { container, getByRole } = render(<OpeningScreen />);
    fireEvent.click(container.firstElementChild!);
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('fading');
    act(() => { vi.advanceTimersByTime(FADE_MS); });
    fireEvent.click(getByRole('button', { name: "Rejouer l’intro" }));
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('intro');
    fireEvent.keyDown(window, { key: ' ' });
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('fading');
  });

  it('ne rejoue pas l’intro quand on revient sur l’accueil dans le même chargement', () => {
    const first = render(<OpeningScreen />);
    first.unmount();
    const { container } = render(<OpeningScreen />);
    expect(container.firstElementChild?.getAttribute('data-phase')).toBe('menu');
  });
});
