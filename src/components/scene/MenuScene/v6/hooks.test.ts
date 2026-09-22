import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import type { SceneMeta } from '@/lib/assets';
import { hooks } from './hooks';

const meta: SceneMeta = {
  version: '6.0', camera: { position: [-2.8, 4.3, -2.8], target: [-40, 4.3, -7.5], fov: 76 }, up: [0, 0, 1],
  background: '#4a6a8c', animations: ['Animated_Background_6_0'],
};

/** Un groupe de trois primitives dans l'ordre du xdb, dont un dôme à alpha de sommet nul. */
function scene() {
  const root = new THREE.Group();
  const group = new THREE.Group(); root.add(group);
  const make = (element: string, alpha: number) => {
    const geometry = new THREE.PlaneGeometry();
    geometry.userData.element = element;
    const count = geometry.getAttribute('position').count;
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(Array(count).fill([1, 1, 1, alpha]).flat(), 4));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true }));
    mesh.renderOrder = -99; group.add(mesh);
    return mesh;
  };
  return { root, sky: make('Sky_Back', 0), clouds: make('Clouds_Ring_01', 1), lab: make('Lab', 1) };
}

describe('V6 hooks', () => {
  it("redresse les textures dont l'origine est en bas dans le client", () => {
    const texture = new THREE.Texture();
    hooks.prepareTexture!(texture);
    expect(texture.repeat.y).toBe(-1);
    expect(texture.offset.y).toBe(1);
  });
  it("peint dans l'ordre du xdb et rend visible le dôme à alpha nul", () => {
    const { root, sky, clouds, lab } = scene();
    const effects = hooks.createEffects!(root, meta, () => new THREE.Texture());
    expect(effects).not.toBeNull();
    expect([sky.renderOrder, clouds.renderOrder, lab.renderOrder]).toEqual([0, 1, 2]);
    expect((sky.material as THREE.Material).customProgramCacheKey()).toBe('v6-opaque-vertex-alpha');
    expect((lab.material as THREE.Material).customProgramCacheKey()).not.toBe('v6-opaque-vertex-alpha');
    expect(() => { effects!.update(1); effects!.dispose(); }).not.toThrow();
  });
});
