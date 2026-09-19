import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import type { ArchiveEntry } from '@/lib/assets';
import { ChroniclesScreen } from './ChroniclesScreen';

const ENTRIES: ArchiveEntry[] = [
  {
    version: '1.1', label: 'Allods Online (1.1)', media: 'image', background: 'background.png',
    note: 'écran recomposé', background_note: 'capture de la scène 3D à venir (illustration de repli)',
    theme: { name: 'MainTitle', duration: 168.046, ogg: 'theme.ogg', mp3: 'theme.mp3' },
  },
  { version: '5.0', name: 'Heart of the World', label: 'Allods Online - Heart of the World (5.0)', media: null },
  {
    version: '8.0', name: 'Immortality', label: 'Allods Online - Immortality (8.0)',
    media: 'image', background: 'background.png', logo: 'logo.png',
    theme: { name: 'MainMenu_Immortality', duration: 182.687, ogg: 'theme.ogg', mp3: 'theme.mp3' },
  },
  {
    version: '11.0', name: 'Soul of Darkness', label: 'Allods Online - Soul of Darkness (11.0)',
    media: 'video', video: { webm: 'menu.webm', mp4: 'menu.mp4' },
    theme_note: 'Thème non disponible dans les clients archivés',
  },
  {
    version: '16.0', name: 'Power of Metal', label: 'Allods Online - Power of Metal (16.0)',
    media: 'video', video: { webm: 'menu.webm', mp4: 'menu.mp4' }, logo: 'logo.png',
    theme: { name: 'MainMenu_ThePowerOfMetal', duration: 169.846, ogg: 'theme.ogg', mp3: 'theme.mp3' },
  },
];

vi.mock('@/lib/assets', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/assets')>();
  return { ...actual, archiveEntries: () => ENTRIES };
});

const navigateSpy = vi.fn();
vi.mock('@/lib/router', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/router')>();
  return {
    ...actual,
    navigate: (...args: Parameters<typeof actual.navigate>) => { navigateSpy(...args); actual.navigate(...args); },
  };
});

const playSfx = vi.fn();
const playExternal = vi.fn();
const pauseMusic = vi.fn();
const resumeAmbient = vi.fn();
// Lecture réelle rapportée par le moteur : les tests la pilotent (le vrai moteur est
// éprouvé par `ChroniclesScreen.autoplay.test.tsx` et `AudioProvider.test.tsx`).
const engine = { playing: false, external: null as string | null };
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({
    muted: false, track: 'ambient', external: engine.external, paused: false, playing: engine.playing, ready: true,
    toggleMuted: vi.fn(), setTrack: vi.fn(), playSfx, playExternal, pauseMusic, resumeAmbient,
  }),
}));

beforeEach(() => {
  [navigateSpy, playSfx, playExternal, pauseMusic, resumeAmbient].forEach(fn => fn.mockClear());
  engine.playing = false;
  engine.external = null;
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
});

function setup(search = '?v=8.0') {
  window.history.pushState(null, '', `/chroniques${search}`);
  return render(<ChroniclesScreen />);
}

describe('ChroniclesScreen — frise des versions', () => {
  it('rend une pilule par version et met en surbrillance celle de `?v=`', () => {
    const { getAllByTestId } = setup();
    const pills = getAllByTestId('version-pill');
    expect(pills).toHaveLength(ENTRIES.length);
    expect(pills.filter(el => el.getAttribute('aria-current') === 'true').map(el => el.textContent)).toEqual(['8.0']);
  });

  it('affiche le cartouche de la version active, sans ses notes techniques', () => {
    const { getAllByText, queryByText } = setup('?v=1.1');
    // 1.1 n'a pas de logo : le libellé est aussi le grand titre, d'où les deux occurrences.
    expect(getAllByText('Allods Online (1.1)').length).toBe(2);
    expect(queryByText('écran recomposé')).toBeNull();
    expect(queryByText('capture de la scène 3D à venir (illustration de repli)')).toBeNull();
  });

  it('ouvre sur la version la plus récente quand `?v=` est absent ou inconnu', () => {
    const { getByText, unmount } = setup('');
    expect(getByText('Allods Online - Power of Metal (16.0)')).toBeTruthy();
    unmount();
    expect(setup('?v=42.0').getByText('Allods Online - Power of Metal (16.0)')).toBeTruthy();
  });

  it('→ passe à la version suivante et met `?v=` à jour', () => {
    const { getAllByText } = setup();
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(window.location.search).toBe('?v=11.0');
    expect(getAllByText('Allods Online - Soul of Darkness (11.0)').length).toBe(2);
  });

  it('← revient à la version précédente', () => {
    const { getAllByText } = setup();
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(window.location.search).toBe('?v=5.0');
    expect(getAllByText('Allods Online - Heart of the World (5.0)').length).toBe(2);
  });

  it('ne dépasse pas les extrémités de la frise', () => {
    setup('?v=1.1');
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(window.location.search).toBe('?v=1.1');
  });

  it('affiche « Média non extrait » pour une version sans média', () => {
    const { getByText } = setup('?v=5.0');
    expect(getByText('Média non extrait')).toBeTruthy();
  });
});

describe('ChroniclesScreen — logo et emblème', () => {
  it("affiche le logo de la version, et pas de titre en toutes lettres", () => {
    const { getByTestId, queryByTestId } = setup('?v=16.0');
    const logo = getByTestId('version-logo') as HTMLImageElement;
    expect(logo.getAttribute('src')).toBe('/game/archive/16.0/logo.png');
    expect(logo.getAttribute('alt')).toBe('Allods Online - Power of Metal (16.0)');
    expect(queryByTestId('version-title')).toBeNull();
  });

  it('remplace le logo absent par le libellé en grand', () => {
    const { getByTestId, queryByTestId } = setup('?v=1.1');
    expect(queryByTestId('version-logo')).toBeNull();
    expect(getByTestId('version-title').textContent).toBe('Allods Online (1.1)');
  });


  it('signale un thème indisponible sans tenter de le jouer', () => {
    const { getByText, getByLabelText } = setup('?v=11.0');
    expect(getByText('Thème non disponible')).toBeTruthy();
    expect((getByLabelText('Thème indisponible') as HTMLButtonElement).disabled).toBe(true);
    expect(playExternal).not.toHaveBeenCalled();
  });
});

describe('ChroniclesScreen — audio et fermeture', () => {
  it("joue « medals-open » et met l'ambiance du site en pause au montage", () => {
    setup();
    expect(playSfx).toHaveBeenCalledWith('medals-open');
    expect(pauseMusic).toHaveBeenCalled();
  });

  it('joue le thème de la version active via le moteur audio', () => {
    setup();
    expect(playExternal).toHaveBeenCalledWith(
      'archive:8.0',
      { ogg: '/game/archive/8.0/theme.ogg', mp3: '/game/archive/8.0/theme.mp3' },
      expect.objectContaining({ loop: true }),
    );
  });

  it("reprend l'ambiance du site au démontage", () => {
    const { unmount } = setup();
    expect(resumeAmbient).not.toHaveBeenCalled();
    unmount();
    expect(resumeAmbient).toHaveBeenCalled();
  });

  it('met le thème en pause puis le relance par le bouton du lecteur', () => {
    engine.playing = true;
    engine.external = 'archive:8.0';
    const { getByLabelText, rerender } = setup();
    fireEvent.click(getByLabelText('Mettre le thème en pause'));
    expect(pauseMusic).toHaveBeenCalledTimes(2); // montage + bouton

    engine.playing = false;
    rerender(<ChroniclesScreen />);
    playExternal.mockClear();
    fireEvent.click(getByLabelText('Lire le thème'));
    expect(playExternal).toHaveBeenCalledWith('archive:8.0', expect.anything(), expect.anything());
  });

  it("n'annonce pas la lecture du thème quand le moteur joue autre chose", () => {
    engine.playing = true;
    engine.external = null;          // l'ambiance du site, pas le thème de la version
    const { getByLabelText } = setup();
    expect(getByLabelText('Lire le thème')).toBeTruthy();
  });

  it('la croix joue « medals-close » et revient à l\'accueil', () => {
    const { getByLabelText } = setup();
    playSfx.mockClear();
    fireEvent.click(getByLabelText('Fermer'));
    expect(playSfx).toHaveBeenCalledWith('medals-close');
    expect(navigateSpy).toHaveBeenCalledWith('/');
  });
});
