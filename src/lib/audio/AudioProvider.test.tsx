import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { AudioProvider, MUTE_KEY, VOLUME_KEY } from './AudioProvider';
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
  it('applique et mémorise le volume sans modifier la position ni la pause', () => {
    const { getByTestId } = setup();
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    const el = getByTestId('music-a') as HTMLAudioElement;
    el.currentTime = 42;
    act(() => { api!.pauseMusic(); api!.setVolume(.4); });
    expect(el.volume).toBeCloseTo(.12);
    expect(el.currentTime).toBe(42);
    expect(api!.paused).toBe(true);
    expect(window.localStorage.getItem(VOLUME_KEY)).toBe('0.4');
    act(() => { api!.toggleMuted(); api!.toggleMuted(); });
    expect(api!.volume).toBe(.4);
    expect(el.volume).toBeCloseTo(.12);
    act(() => { api!.setVolume(2); });
    expect(api!.volume).toBe(1);
    act(() => { api!.setVolume(-1); });
    expect(api!.volume).toBe(0);
    act(() => { api!.setVolume(Number.NaN); });
    expect(api!.volume).toBe(0);
  });
  it('restaure un volume sauvegardé et le conserve pendant les fondus', () => {
    useFakeAnimationClock();
    window.localStorage.setItem(VOLUME_KEY, '0.5');
    const { getByTestId } = setup();
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.playExternal('a', { ogg: '/a.ogg', mp3: '/a.mp3' }, { crossfadeMs: 600 }); });
    act(() => { vi.advanceTimersByTime(300); api!.setVolume(.2); });
    act(() => { vi.advanceTimersByTime(400); });
    expect((getByTestId('music-b') as HTMLAudioElement).volume).toBeCloseTo(.06);
    act(() => { api!.playSfx('ui-click'); });
    const sfx = document.querySelector('audio:not([data-testid])') as HTMLAudioElement;
    expect(sfx.volume).toBeCloseTo(.1);
    act(() => { api!.setVolume(.4); });
    expect(sfx.volume).toBeCloseTo(.2);
  });
  it('seek borne la position et conserve la pause sans relancer le morceau', () => {
    const { getByTestId } = setup();
    act(() => { api!.playExternal('music:a', { ogg: '/a.ogg', mp3: '/a.mp3' }); });
    const el = getByTestId('music-a') as HTMLAudioElement;
    Object.defineProperty(el, 'duration', { value: 120, configurable: true });
    act(() => { api!.pauseMusic(); api!.seekMusic(50); });
    expect(el.currentTime).toBe(50);
    expect(api!.paused).toBe(true);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    act(() => { api!.seekMusic(999); });
    expect(el.currentTime).toBe(120);
    act(() => { api!.seekMusic(-10); });
    expect(el.currentTime).toBe(0);
    act(() => { api!.seekMusic(Number.NaN); });
    expect(el.currentTime).toBe(0);
  });
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

  it("ne sort jamais du domaine [0, 1] quand rAF rappelle avec un horodatage antérieur au départ du fondu", () => {
    // Le timestamp passé à un rAF est celui du **début de la frame** : il peut précéder
    // le `performance.now()` lu au lancement du fondu, d'où un `t` négatif et un volume
    // hors domaine (le navigateur lève alors une IndexSizeError). Constaté en vrai sur
    // les fondus courts (600 ms) de la page Chroniques.
    vi.useFakeTimers();
    let clock = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => clock);
    vi.stubGlobal('requestAnimationFrame', ((cb: (time: number) => void) => setTimeout(() => { clock += 16; cb(clock - 50); }, 16)) as unknown as typeof requestAnimationFrame);
    vi.stubGlobal('cancelAnimationFrame', ((id: number) => clearTimeout(id)) as unknown as typeof cancelAnimationFrame);

    const { getByTestId } = setup();
    const menuEl = getByTestId('music-a') as HTMLAudioElement;
    const ambientEl = getByTestId('music-b') as HTMLAudioElement;
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.setTrack('ambient', { crossfadeMs: 600 }); });
    act(() => { vi.advanceTimersByTime(700); });

    expect(ambientEl.volume).toBeGreaterThanOrEqual(0);
    expect(menuEl.volume).toBeGreaterThanOrEqual(0);
  });

  it("playExternal joue une source hors index sans effacer la piste du site", () => {
    useFakeAnimationClock();
    const { getByTestId } = setup();
    const menuEl = getByTestId('music-a') as HTMLAudioElement;
    const themeEl = getByTestId('music-b') as HTMLAudioElement;

    act(() => { window.dispatchEvent(new Event('pointerdown')); }); // démarre `menu` sur A
    act(() => { api!.pauseMusic(); });
    expect(api!.paused).toBe(true);

    act(() => { api!.playExternal('archive:8.0', { ogg: '/game/archive/8.0/theme.ogg', mp3: '/game/archive/8.0/theme.mp3' }, { loop: true, crossfadeMs: 600 }); });
    expect(api!.external).toBe('archive:8.0');
    expect(api!.track).toBe('menu');        // mémorisée pour la sortie de la page
    expect(themeEl.querySelector('source')?.getAttribute('src')).toBe('/game/archive/8.0/theme.ogg');
    expect(themeEl.loop).toBe(true);

    act(() => { vi.advanceTimersByTime(700); });
    expect(themeEl.volume).toBeCloseTo(0.3, 5);
    expect(menuEl.volume).toBeCloseTo(0, 5);
  });

  it("`ended` signale la fin d'une source externe non bouclée, puis s'efface à la suivante", () => {
    useFakeAnimationClock();
    const { getByTestId } = setup();
    const themeEl = getByTestId('music-b') as HTMLAudioElement;
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.playExternal('archive:8.0', { ogg: '/a.ogg', mp3: '/a.mp3' }, { loop: false, crossfadeMs: 0 }); });
    expect(api!.ended).toBeNull();

    act(() => { themeEl.dispatchEvent(new Event('ended')); });
    expect(api!.ended).toBe('archive:8.0');
    expect(api!.playing).toBe(false);

    act(() => { api!.playExternal('archive:9.0', { ogg: '/b.ogg', mp3: '/b.mp3' }, { loop: false, crossfadeMs: 0 }); });
    expect(api!.ended).toBeNull();
  });

  it("resumeAmbient revient à la piste du site sans la rembobiner", () => {
    useFakeAnimationClock();
    const { getByTestId } = setup();
    const menuEl = getByTestId('music-a') as HTMLAudioElement;
    const themeEl = getByTestId('music-b') as HTMLAudioElement;
    // jsdom ne gère pas `currentTime` : on l'instrumente pour vérifier l'absence de rembobinage.
    let position = 0;
    Object.defineProperty(menuEl, 'currentTime', { get: () => position, set: (v: number) => { position = v; }, configurable: true });

    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.pauseMusic(); });
    position = 42;
    act(() => { api!.playExternal('archive:8.0', { ogg: '/a.ogg', mp3: '/a.mp3' }, { loop: true, crossfadeMs: 600 }); });
    act(() => { vi.advanceTimersByTime(700); });

    const pauseSpy = vi.spyOn(themeEl, 'pause');
    act(() => { api!.resumeAmbient({ crossfadeMs: 600 }); });
    act(() => { vi.advanceTimersByTime(700); });

    expect(api!.external).toBeNull();
    expect(api!.paused).toBe(false);
    expect(position).toBe(42);
    expect(menuEl.volume).toBeCloseTo(0.3, 5);
    expect(pauseSpy).toHaveBeenCalled();
  });

  it('resumeAmbient ne joue rien si le site n\'avait pas encore de piste', () => {
    setup();
    act(() => { api!.resumeAmbient(); });
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('restaure la source et la position du site après plusieurs pistes externes', () => {
    const { getByTestId } = setup();
    const a = getByTestId('music-a') as HTMLAudioElement;
    const b = getByTestId('music-b') as HTMLAudioElement;
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    a.currentTime = 42;
    act(() => { api!.pauseMusic(); });
    act(() => { api!.playExternal('music:a', { ogg: '/a.ogg', mp3: '/a.mp3' }, { crossfadeMs: 0 }); });
    act(() => { api!.playExternal('music:b', { ogg: '/b.ogg', mp3: '/b.mp3' }, { crossfadeMs: 0 }); });
    act(() => { api!.resumeAmbient({ crossfadeMs: 0 }); });
    expect(b.querySelector('source')?.getAttribute('src')).toBe('/game/audio/menu.ogg');
    expect(b.currentTime).toBe(42);
    expect(api!.external).toBeNull();
  });

  it('pauseMusic arrête les deux pistes pendant un fondu', () => {
    useFakeAnimationClock();
    const { getByTestId } = setup();
    act(() => { window.dispatchEvent(new Event('pointerdown')); });
    act(() => { api!.playExternal('music:a', { ogg: '/a.ogg', mp3: '/a.mp3' }); });
    const a = vi.fn();
    const b = vi.fn();
    (getByTestId('music-a') as HTMLAudioElement).pause = a;
    (getByTestId('music-b') as HTMLAudioElement).pause = b;
    act(() => { api!.pauseMusic(); });
    expect(a).toHaveBeenCalledOnce();
    expect(b).toHaveBeenCalledOnce();
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
