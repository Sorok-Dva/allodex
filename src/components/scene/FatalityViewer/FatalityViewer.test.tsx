import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { createRef } from 'react';
import * as THREE from 'three';
import { FatalityViewer, effectBounds, skyBehindEverything, toViewerMaterial, type FatalityViewerHandle } from './FatalityViewer';
import type { FatalityObject } from './timeline';
import type { FatalityTimeline } from './timeline';
import type { LoadedScene, SceneLoader } from '@/components/scene/MenuScene';

/** Un glTF minimal : un triangle et un ou deux clips d'une seconde. */
function fakeGltf(names: string[]): LoadedScene & { mesh: THREE.Mesh } {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: new THREE.Texture() }));
  mesh.name = 'body';
  const root = new THREE.Group();
  root.add(mesh);
  const animations = names.map((name, i) => new THREE.AnimationClip(name, 1 + i, [
    new THREE.VectorKeyframeTrack('body.position', [0, 1 + i], [0, 0, 0, 0, 0, 5]),
  ]));
  return { scene: root, animations, mesh };
}

function fakeRenderer() {
  return {
    outputColorSpace: '',
    capabilities: { getMaxAnisotropy: () => 8 },
    setPixelRatio: vi.fn(),
    setSize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
  };
}

/** Chronologie minimale : le clip d'une seconde puis sa pose tenue, fondu final à 1,5-2 s. */
const TIMELINE: FatalityTimeline = {
  end: 1, victim: [{ t: 0, end: 1, anim: 'DeathFatalityWarrior', speed: 1, mode: 'CLAMP' }],
  scale: [], alpha: [], spawns: [], attached: [],
};

let renderer: ReturnType<typeof fakeRenderer>;
let loader: { load: ReturnType<typeof vi.fn> };
let raf: FrameRequestCallback | null;

beforeEach(() => {
  renderer = fakeRenderer();
  loader = { load: vi.fn() };
  raf = null;
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { raf = cb; return 1; });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

describe('skyBehindEverything', () => {
  it('draws sky layers first, farthest first, without depth test but still blended', () => {
    const sky = new THREE.Group();
    const near = new THREE.Mesh(new THREE.SphereGeometry(104), new THREE.MeshBasicMaterial({ transparent: true }));
    const far = new THREE.Mesh(new THREE.SphereGeometry(585), new THREE.MeshBasicMaterial());
    sky.add(near, far);
    skyBehindEverything(sky);
    expect(far.renderOrder).toBeLessThan(near.renderOrder);
    expect(near.renderOrder).toBeLessThan(0);
    const material = near.material as THREE.MeshBasicMaterial;
    expect(material.depthTest).toBe(false);
    expect(material.transparent).toBe(false);
    expect(material.blending).toBe(THREE.CustomBlending);
    expect(material.blendDst).toBe(THREE.OneMinusSrcAlphaFactor);
  });
});

describe('toViewerMaterial', () => {
  it('éclaire les matériaux opaques et laisse les additifs sans éclairage', () => {
    const opaque = toViewerMaterial(new THREE.MeshBasicMaterial({ map: new THREE.Texture() }));
    expect(opaque).toBeInstanceOf(THREE.MeshLambertMaterial);
    expect(opaque.transparent).toBe(false);
    const additive = new THREE.MeshBasicMaterial({ transparent: true });
    additive.userData = { blend: 'add' };
    const fx = toViewerMaterial(additive);
    expect(fx).toBeInstanceOf(THREE.MeshBasicMaterial);
    expect(fx.blending).toBe(THREE.AdditiveBlending);
    expect(fx.depthWrite).toBe(false);
  });
});

describe('FatalityViewer', () => {
  async function mount(fxUrl: string | null = '/game/fatalities/fx/warrior.glb') {
    const ref = createRef<FatalityViewerHandle>();
    const onProgress = vi.fn();
    const onEnded = vi.fn();
    const view = render(
      <FatalityViewer
        ref={ref}
        characterUrl="/game/fatalities/characters/aed-female.glb"
        model="AedFemale"
        fxUrl={fxUrl}
        timeline={TIMELINE}
        objects={{}}
        fadeStart={1.5}
        fadeDuration={0.5}
        height={2}
        playing
        loop={false}
        speed={1}
        showFx
        onProgress={onProgress}
        onEnded={onEnded}
        createLoader={() => loader as unknown as SceneLoader}
        createRenderer={() => renderer as unknown as THREE.WebGLRenderer}
      />,
    );
    await act(async () => {});
    return { ...view, ref, onProgress, onEnded };
  }

  it('charge le personnage et l’effet par le chargeur injecté', async () => {
    const { getByTestId } = await mount();
    expect(getByTestId('fatality-viewer').tagName).toBe('CANVAS');
    const urls = loader.load.mock.calls.map(call => call[0]);
    expect(urls).toEqual(['/game/fatalities/characters/aed-female.glb', '/game/fatalities/fx/warrior.glb']);
  });

  it('joue la chronologie, rapporte la progression et s’arrête à la fin hors boucle', async () => {
    const { onProgress, onEnded } = await mount(null);
    await act(async () => { loader.load.mock.calls[0][1](fakeGltf(['DeathFatality', 'DeathFatalityWarrior'])); });
    expect(raf).not.toBeNull();
    let now = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    await act(async () => { raf!(now); });         // première image : delta nul
    now += 200;
    await act(async () => { raf!(now); });
    expect(renderer.render).toHaveBeenCalled();
    expect(onProgress).toHaveBeenLastCalledWith(expect.closeTo(0.2, 2), 2);
    // Un pas est plafonné à 0,25 s (onglet revenu au premier plan) : on avance par petits pas.
    for (let i = 0; i < 12; i += 1) { now += 200; await act(async () => { raf!(now); }); }
    expect(onEnded).toHaveBeenCalledTimes(1);   // au-delà de la durée (2 s) : fin signalée une fois
    expect(onProgress).toHaveBeenLastCalledWith(2, 2);
  });

  it('expose seek et resetView', async () => {
    const { ref, onProgress } = await mount(null);
    await act(async () => { loader.load.mock.calls[0][1](fakeGltf(['DeathFatalityWarrior'])); });
    let now = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    await act(async () => { raf!(now); });
    ref.current!.seek(0.75);
    now += 1;
    await act(async () => { raf!(now); });
    expect(onProgress.mock.calls.at(-1)![0]).toBeCloseTo(0.75, 2);
    expect(() => ref.current!.resetView()).not.toThrow();
  });
});

describe('effectBounds', () => {
  const obj = (over: Partial<FatalityObject>): FatalityObject => ({ fadeIn: 0, fadeOut: 0, scale: 1, duration: 0, loop: false, ...over });
  const timeline = (spawns: FatalityTimeline['spawns']): FatalityTimeline => ({ end: 1, victim: [], scale: [], alpha: [], spawns, attached: [] });

  it('frames the sound-bearing effect with its components, above ground, mirrored in X', () => {
    const objects = {
      Main: obj({ sound: 'fx/Main', bounds: [1, 0, -2, 1, 1, 4], components: [{ vot: 'Child', locator: '' }] }),
      Child: obj({ bounds: [0, 0, 6, 1, 1, 1] }),
      Back: obj({ bounds: [0, 6.7, 20.8, 2, 0, 2] }),
    };
    const box = effectBounds(timeline([
      { t: 0, vot: 'Main', lifeTime: 5, scale: 2, offset: [0, 0, 0] },
      { t: 0, vot: 'Back', lifeTime: 5, scale: 0.5, offset: [0, 0, 1] },
    ]), objects, 1.8)!;
    expect(box.min.toArray()).toEqual([-4, -2, 0]);
    expect(box.max.toArray()).toEqual([2, 2, 14]);
  });

  it('uses every effect without a sound, and returns null without any box', () => {
    const objects = { A: obj({ bounds: [0, 0, 1, 1, 1, 1] }), B: obj({}) };
    expect(effectBounds(timeline([{ t: 0, vot: 'A', lifeTime: 1, scale: 1 }]), objects, 1.8)!.max.z).toBe(2);
    expect(effectBounds(timeline([{ t: 0, vot: 'B', lifeTime: 1, scale: 1 }]), objects, 1.8)).toBeNull();
  });
});
