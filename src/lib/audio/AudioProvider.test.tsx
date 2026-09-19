import { describe, it, expect, vi, beforeEach } from 'vitest';
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
});
