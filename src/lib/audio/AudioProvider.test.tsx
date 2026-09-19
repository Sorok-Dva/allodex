import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { AudioProvider, MUTE_KEY } from './AudioProvider';
import { useGameAudio } from './useGameAudio';
import type { GameAudio } from './AudioProvider';

// `audioMeta`/`audioSrc` viennent normalement de `public/game/audio.json`, chargé par
// `loadManifest()` (jamais appelé dans ces tests) : on fixe des métadonnées connues
// pour isoler le moteur audio de l'index réel.
vi.mock('@/lib/assets', () => ({
  audioMeta: (name: string) =>
    name === 'menu' || name === 'ambient'
      ? { duration: 150, loop: true }
      : name === 'ui-click'
        ? { duration: 0.02, loop: false }
        : undefined,
  audioSrc: (name: string) => ({ ogg: `/game/audio/${name}.ogg`, mp3: `/game/audio/${name}.mp3` }),
}));

let api: GameAudio | null = null;
function Probe() {
  api = useGameAudio();
  return null;
}

function setup() {
  api = null;
  return render(<AudioProvider><Probe /></AudioProvider>);
}

beforeEach(() => {
  window.localStorage.clear();
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
});

// Filet de sécurité pour les tests à horloge/rAF factices ci-dessous : on revient
// toujours à des timers réels et des globales non stubées, même si un test échoue.
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Installe une horloge factice pour `performance.now()` et un `requestAnimationFrame`
 * asservi au fake timer de vitest (un `setTimeout` de 16 ms qui avance l'horloge lui-
 * même) : `vi.useFakeTimers()` seul ne fait pas avancer `performance.now()` en
 * lock-step avec `vi.advanceTimersByTime()`, ce qui bloquerait le fondu à `t≈0`.
 */
function useFakeAnimationClock() {
  vi.useFakeTimers();
  let clock = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
  vi.stubGlobal('requestAnimationFrame', ((cb: (time: number) => void) => setTimeout(() => { clock += 16; cb(clock); }, 16)) as unknown as typeof requestAnimationFrame);
  vi.stubGlobal('cancelAnimationFrame', ((id: number) => clearTimeout(id)) as unknown as typeof cancelAnimationFrame);
}

describe('AudioProvider / useGameAudio', () => {
  it("ne joue rien avant un geste utilisateur", () => {
    setup();
    act(() => { api!.setTrack('menu'); });
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(api!.track).toBe('menu');
  });

  it('démarre la piste menu au premier pointerdown si le son est actif', () => {
    setup();
    act(() => { api!.setTrack('menu'); });
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it('ne relance jamais automatiquement si le son était coupé au chargement', () => {
    window.localStorage.setItem(MUTE_KEY, '1');
    setup();
    expect(api!.muted).toBe(true);
    act(() => { api!.setTrack('menu'); });
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('toggleMuted persiste dans localStorage', () => {
    setup();
    act(() => { api!.toggleMuted(); });
    expect(api!.muted).toBe(true);
    expect(window.localStorage.getItem(MUTE_KEY)).toBe('1');
    act(() => { api!.toggleMuted(); });
    expect(api!.muted).toBe(false);
    expect(window.localStorage.getItem(MUTE_KEY)).toBe('0');
  });

  it('playSfx ne fait rien quand le son est coupé', () => {
    setup();
    act(() => { api!.toggleMuted(); });
    const before = document.querySelectorAll('audio').length;
    act(() => { api!.playSfx('ui-click'); });
    expect(document.querySelectorAll('audio').length).toBe(before);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('playSfx ne fait rien quand les métadonnées sont absentes', () => {
    setup();
    const before = document.querySelectorAll('audio').length;
    act(() => { api!.playSfx('inconnu'); });
    expect(document.querySelectorAll('audio').length).toBe(before);
  });

  it('playSfx crée un élément <audio> et le joue quand le son est actif', () => {
    setup();
    const before = document.querySelectorAll('audio').length;
    act(() => { api!.playSfx('ui-click'); });
    expect(document.querySelectorAll('audio').length).toBe(before + 1);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("setTrack('ambient') change la piste courante", () => {
    setup();
    act(() => { api!.setTrack('ambient'); });
    expect(api!.track).toBe('ambient');
  });

  it("termine le fondu croisé après ~1500 ms : la sortante se met en pause à volume 0, l'entrante atteint MUSIC_VOLUME", () => {
    useFakeAnimationClock();
    const { getByTestId } = setup();
    const menuEl = getByTestId('music-a') as HTMLAudioElement;
    const ambientEl = getByTestId('music-b') as HTMLAudioElement;
    const pauseSpy = vi.spyOn(menuEl, 'pause');

    act(() => { api!.setTrack('menu'); });
    act(() => { window.dispatchEvent(new Event('pointerdown')); }); // geste -> menu démarre réellement
    act(() => { api!.setTrack('ambient'); }); // lance le fondu croisé menu -> ambient

    act(() => { vi.advanceTimersByTime(1600); }); // dépasse les 1500 ms par défaut

    expect(ambientEl.volume).toBeCloseTo(0.3, 5); // MUSIC_VOLUME
    expect(menuEl.volume).toBeCloseTo(0, 5);
    expect(pauseSpy).toHaveBeenCalled();
  });

  it('annule le fondu en cours (aucune mutation de volume après) quand AudioProvider est démonté', () => {
    useFakeAnimationClock();
    const { getByTestId, unmount } = setup();
    const ambientEl = getByTestId('music-b') as HTMLAudioElement;

    act(() => { api!.setTrack('menu'); });
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.setTrack('ambient'); });

    act(() => { vi.advanceTimersByTime(750); }); // à mi-parcours du fondu de 1500 ms
    const midVolume = ambientEl.volume;
    expect(midVolume).toBeGreaterThan(0);
    expect(midVolume).toBeLessThan(0.3);

    unmount(); // doit annuler le rAF/tick en cours (`useEffect(() => stopFade, [stopFade])`)

    act(() => { vi.advanceTimersByTime(3000); }); // laisserait le fondu se terminer si non annulé
    expect(ambientEl.volume).toBe(midVolume);
  });
});
