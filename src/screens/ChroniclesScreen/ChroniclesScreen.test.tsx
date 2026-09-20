import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
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

vi.mock('@/data/versions.json', () => ({
  default: {
    _note: 'doc',
    '8.0': { release: '2016-11', lore: { fr: 'Les dieux reviennent.', en: 'The gods return.' }, changes: { fr: ['niveau maximum porté à 75', 'nouvelle zone'], en: ['level cap raised to 75'] } },
  },
}));

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
const engine = { playing: false, external: null as string | null, ended: null as string | null };
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({
    muted: false, track: 'ambient', external: engine.external, ended: engine.ended, paused: false, playing: engine.playing, ready: true,
    toggleMuted: vi.fn(), setTrack: vi.fn(), playSfx, playExternal, pauseMusic, resumeAmbient,
  }),
}));

beforeEach(() => {
  [navigateSpy, playSfx, playExternal, pauseMusic, resumeAmbient].forEach(fn => fn.mockClear());
  engine.playing = false;
  engine.external = null;
  engine.ended = null;
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
});

function setup(search = '?v=8.0') {
  window.history.pushState(null, '', `/chronicles${search}`);
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
      expect.objectContaining({ loop: false }),
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

describe('ChroniclesScreen — défilement automatique', () => {
  it('passe à la version suivante quand le thème arrive au bout', () => {
    engine.ended = 'archive:8.0';
    setup('?v=8.0');
    expect(navigateSpy).toHaveBeenCalledWith('/chronicles?v=11.0', { replace: true });
  });

  it('ne bouge pas tant que le thème joue ou si c\'est un autre thème qui a fini', () => {
    engine.ended = 'archive:1.1';
    setup('?v=8.0');
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('une version sans thème laisse la main après le temps d\'affichage, et la dernière ramène à la première', () => {
    vi.useFakeTimers();
    try {
      setup('?v=11.0');
      act(() => { vi.advanceTimersByTime(19_999); });
      expect(navigateSpy).not.toHaveBeenCalled();
      act(() => { vi.advanceTimersByTime(1); });
      expect(navigateSpy).toHaveBeenCalledWith('/chronicles?v=16.0', { replace: true });

      navigateSpy.mockClear();
      engine.ended = 'archive:16.0';
      setup('?v=16.0');
      expect(navigateSpy).toHaveBeenCalledWith('/chronicles?v=1.1', { replace: true });
    } finally {
      vi.useRealTimers();
    }
  });

  it('un thème mis en pause suspend l\'enchaînement', () => {
    engine.playing = true;
    engine.external = 'archive:8.0';
    const { getByLabelText, rerender } = setup('?v=8.0');
    fireEvent.click(getByLabelText('Mettre le thème en pause'));
    engine.ended = 'archive:8.0';
    rerender(<ChroniclesScreen />);
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});

describe('ChroniclesScreen — panneau « À propos de cette version »', () => {
  it('le bouton « ? » ouvre la fiche (date, histoire, changements) et la referme', () => {
    const { getByLabelText, getByTestId, queryByTestId, getByText } = setup('?v=8.0');
    expect(queryByTestId('version-info')).toBeNull();
    fireEvent.click(getByLabelText('À propos de cette version'));
    expect(playSfx).toHaveBeenCalledWith('ui-click');
    expect(getByTestId('version-info').textContent).toContain('Allods Online - Immortality (8.0)');
    expect(getByText('novembre 2016')).toBeTruthy();
    expect(getByText('Les dieux reviennent.')).toBeTruthy();
    expect(getByText('niveau maximum porté à 75')).toBeTruthy();
    fireEvent.click(getByLabelText('À propos de cette version'));
    expect(queryByTestId('version-info')).toBeNull();
  });

  it('une version sans fiche affiche « Fiche à venir », et Échap ferme le panneau', () => {
    const { getByLabelText, getByText, queryByTestId } = setup('?v=1.1');
    fireEvent.click(getByLabelText('À propos de cette version'));
    expect(getByText('Fiche à venir.')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(queryByTestId('version-info')).toBeNull();
  });

  it('le défilement automatique attend tant que la fiche est ouverte, puis reprend', () => {
    const { getByLabelText, rerender } = setup('?v=8.0');
    fireEvent.click(getByLabelText('À propos de cette version'));
    engine.ended = 'archive:8.0';
    rerender(<ChroniclesScreen />);
    expect(navigateSpy).not.toHaveBeenCalled();
    fireEvent.click(getByLabelText('À propos de cette version'));
    expect(navigateSpy).toHaveBeenCalledWith('/chronicles?v=11.0', { replace: true });
  });
});
