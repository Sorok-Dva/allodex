import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import * as THREE from 'three';
import { MenuScene, sortByDepth, toMenuMaterial, type LoadedScene, type SceneLoader } from './MenuScene';

const META = {
  version: '7.0',
  up: [0, 0, 1],
  camera: { position: [0, 70, 18], target: [0, -160, 10], fov: 42 },
  background: '#3a2f56',
  animations: ['AMM_Flag_01'],
};

/** Un glTF minimal : un triangle texturé et une animation d'une seconde. */
function fakeGltf(): LoadedScene & { mesh: THREE.Mesh; texture: THREE.Texture } {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
  const texture = new THREE.Texture();
  const material = new THREE.MeshBasicMaterial({ map: texture });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'ship';
  const root = new THREE.Group();
  root.add(mesh);
  const clip = new THREE.AnimationClip('AMM_Flag_01', 1, [
    new THREE.VectorKeyframeTrack('ship.position', [0, 1], [0, 0, 0, 0, 0, 5]),
  ]);
  return { scene: root, animations: [clip], mesh, texture };
}

function fakeRenderer() {
  return {
    outputColorSpace: '',
    sortObjects: false,
    capabilities: { getMaxAnisotropy: () => 16 },
    setPixelRatio: vi.fn(),
    setSize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
  };
}

let renderer: ReturnType<typeof fakeRenderer>;
let loader: { load: ReturnType<typeof vi.fn> };

beforeEach(() => {
  renderer = fakeRenderer();
  loader = { load: vi.fn() };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => META }));
});
// `fetch` et `matchMedia` (absent de jsdom) sont posés par test, jamais laissés en place.
afterEach(() => vi.unstubAllGlobals());

async function mount() {
  const view = render(
    <MenuScene
      glbUrl="/game/archive/7.0/scene.glb"
      metaUrl="/game/archive/7.0/scene.json"
      createLoader={() => loader as unknown as SceneLoader}
      createRenderer={() => renderer as unknown as THREE.WebGLRenderer}
    />,
  );
  await act(async () => {});
  return view;
}

describe('MenuScene', () => {
  it('monte un canvas et demande le .glb au chargeur injecté', async () => {
    const { getByTestId } = await mount();
    expect(getByTestId('menu-scene').tagName).toBe('CANVAS');
    expect(fetch).toHaveBeenCalledWith('/game/archive/7.0/scene.json');
    expect(loader.load).toHaveBeenCalledTimes(1);
    expect(loader.load.mock.calls[0][0]).toBe('/game/archive/7.0/scene.glb');
  });

  it('cadre la caméra avec les valeurs de scene.json (fov vertical, axe Z vers le haut)', async () => {
    const onReady = vi.fn();
    render(
      <MenuScene
        glbUrl="/g.glb"
        metaUrl="/g.json"
        onReady={onReady}
        createLoader={() => loader as unknown as SceneLoader}
        createRenderer={() => renderer as unknown as THREE.WebGLRenderer}
      />,
    );
    await act(async () => {});
    await act(async () => { loader.load.mock.calls[0][1](fakeGltf()); });

    const camera = renderer.render.mock.calls[0][1] as THREE.PerspectiveCamera;
    expect(camera.isPerspectiveCamera).toBe(true);
    expect(camera.fov).toBe(42);
    expect(camera.up.toArray()).toEqual([0, 0, 1]);
    expect(camera.position.toArray()).toEqual([0, 70, 18]);
    expect(renderer.sortObjects).toBe(true);
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  it('libère géométries, matériaux, textures et moteur de rendu au démontage', async () => {
    const gltf = fakeGltf();
    const { unmount } = await mount();
    await act(async () => { loader.load.mock.calls[0][1](gltf); });

    const geometry = vi.spyOn(gltf.mesh.geometry, 'dispose');
    const material = vi.spyOn(gltf.mesh.material as THREE.Material, 'dispose');
    const texture = vi.spyOn(gltf.texture, 'dispose');
    unmount();
    expect(geometry).toHaveBeenCalled();
    expect(material).toHaveBeenCalled();
    expect(texture).toHaveBeenCalled();
    expect(renderer.dispose).toHaveBeenCalled();
  });

  it('mouvement réduit : une seule image, à t = 0, sans boucle d’animation', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const raf = vi.spyOn(window, 'requestAnimationFrame');
    await mount();
    await act(async () => { loader.load.mock.calls[0][1](fakeGltf()); });

    expect(renderer.render).toHaveBeenCalledTimes(1);
    expect(raf).not.toHaveBeenCalled();
    raf.mockRestore();
  });

  it('anime en boucle quand le mouvement est autorisé', async () => {
    const raf = vi.spyOn(window, 'requestAnimationFrame');
    await mount();
    await act(async () => { loader.load.mock.calls[0][1](fakeGltf()); });
    expect(raf).toHaveBeenCalled();
    raf.mockRestore();
  });
});

describe('toMenuMaterial', () => {
  it('rend les couleurs de sommet telles quelles, sans espace colorimétrique', () => {
    const source = new THREE.MeshBasicMaterial({ map: new THREE.Texture() });
    source.map!.colorSpace = THREE.SRGBColorSpace;
    const material = toMenuMaterial(source);
    expect(material.vertexColors).toBe(true);
    expect(material.map?.colorSpace).toBe(THREE.NoColorSpace);
    expect(material.blending).toBe(THREE.NormalBlending);
    // Décor peint : empilement à la peintre, sans tampon de profondeur (cf. sortByDepth).
    expect(material.transparent).toBe(true);
    expect(material.depthWrite).toBe(false);
    expect(material.depthTest).toBe(false);
  });

  it('passe en mélange additif sur extras.blend = add', () => {
    const source = new THREE.MeshBasicMaterial();
    source.userData = { blend: 'add' };
    const material = toMenuMaterial(source);
    expect(material.blending).toBe(THREE.AdditiveBlending);
    expect(material.transparent).toBe(true);
    expect(material.depthWrite).toBe(false);
  });

  it('conserve le seuil alpha des matériaux MASK et la double face', () => {
    const source = new THREE.MeshBasicMaterial({ alphaTest: 0.5, side: THREE.DoubleSide });
    const material = toMenuMaterial(source);
    expect(material.alphaTest).toBe(0.5);
    expect(material.side).toBe(THREE.DoubleSide);
  });
});

describe('sortByDepth', () => {
  it('donne le plus petit renderOrder à la primitive la plus lointaine', () => {
    const camera = new THREE.PerspectiveCamera(45, 1, 1, 1000);
    camera.position.set(0, 0, 0);
    camera.lookAt(0, 0, -1);
    const root = new THREE.Group();
    const at = (z: number) => {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array([0, 0, z, 1, 0, z, 0, 1, z]), 3));
      geometry.setIndex([0, 1, 2]);
      const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
      root.add(mesh);
      return mesh;
    };
    const near = at(-10);
    const far = at(-200);
    sortByDepth(root, camera);
    expect(far.renderOrder).toBeLessThan(near.renderOrder);
    expect(Math.round(near.renderOrder)).toBe(-10);
  });
});
