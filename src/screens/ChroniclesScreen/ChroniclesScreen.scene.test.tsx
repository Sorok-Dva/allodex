import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act, screen } from '@testing-library/react';
import type { ArchiveEntry } from '@/lib/assets';
import { ChroniclesScreen } from './ChroniclesScreen';

const ENTRIES: ArchiveEntry[] = [
  {
    version: '7.0', name: 'New Order', label: 'Allods Online - New Order (7.0)',
    media: 'image', background: 'background.png',
    scene: { glb: 'scene.glb', meta: 'scene.json' },
  },
];

vi.mock('@/lib/assets', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/assets')>();
  return { ...actual, archiveEntries: () => ENTRIES };
});

const webgl = { available: true };
vi.mock('@/lib/webgl', () => ({ hasWebGL: () => webgl.available, resetWebGLProbe: vi.fn() }));

// La vraie scène tirerait `three` et un contexte WebGL : ici on n'observe que son montage.
const sceneProps = vi.fn();
vi.mock('@/components/scene/MenuScene', () => ({
  default: (props: { glbUrl: string; metaUrl: string; onReady?: () => void }) => {
    sceneProps(props);
    return <canvas data-testid="menu-scene" />;
  },
}));

vi.mock('@/data/versions.json', () => ({ default: {} }));
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({
    muted: false, track: 'ambient', external: null, ended: null, paused: false, playing: false, ready: true,
    toggleMuted: vi.fn(), setTrack: vi.fn(), playSfx: vi.fn(), playExternal: vi.fn(), pauseMusic: vi.fn(), resumeAmbient: vi.fn(),
  }),
}));

beforeEach(() => {
  webgl.available = true;
  sceneProps.mockClear();
  window.history.pushState(null, '', '/chronicles?v=7.0');
});

describe('ChroniclesScreen — scène de menu', () => {
  it('rend la scène 3D et lui passe les URLs du glb et du méta', async () => {
    render(<ChroniclesScreen />);
    // `MenuScene` est chargé à la demande (import dynamique) : il arrive une micro-tâche
    // plus tard que le reste de l'écran.
    expect(await screen.findByTestId('menu-scene')).toBeTruthy();
    expect(sceneProps).toHaveBeenCalledWith(expect.objectContaining({
      glbUrl: '/game/archive/7.0/scene.glb',
      metaUrl: '/game/archive/7.0/scene.json',
    }));
  });

  it('garde le fond fixe sous la scène, puis l’efface à la première image', async () => {
    render(<ChroniclesScreen />);
    await screen.findByTestId('menu-scene');
    const still = document.querySelector('img[src="/game/archive/7.0/background.png"]') as HTMLImageElement;
    expect(still).toBeTruthy();
    const before = still.className;
    await act(async () => { sceneProps.mock.calls[0][0].onReady(); });
    expect(still.className).not.toBe(before);
  });

  it('sans WebGL : le fond fixe seul, aucune scène montée', async () => {
    webgl.available = false;
    render(<ChroniclesScreen />);
    await act(async () => {});
    expect(document.querySelector('img[src="/game/archive/7.0/background.png"]')).toBeTruthy();
    expect(screen.queryByTestId('menu-scene')).toBeNull();
    expect(sceneProps).not.toHaveBeenCalled();
  });
});
