import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { createV4Fog, fogSpeed } from './v4Fog';

function layer(root: THREE.Object3D, element: string, map: THREE.Texture) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map }));
  mesh.geometry.userData.element = element; root.add(mesh); return mesh;
}
describe('brume 4.0', () => {
  it('emprunte à la 7.0 des vitesses de l’ordre de la brume et des nuages, sans toucher au décor', () => {
    expect(fogSpeed('fog')![0]).toBeCloseTo(.05);
    expect(fogSpeed('Clouds_012')![0]).toBeCloseTo(.01);
    expect(fogSpeed('Back3')).toBeDefined();
    expect(fogSpeed('sun_rays_01')![0]).toBeCloseTo(.04); expect(fogSpeed('Sun_Rays_02')![0]).toBeCloseTo(.04);
    for (const e of ['Back2', 'Water', 'castle', 'Sun', 'birds2_birds1']) expect(fogSpeed(e)).toBeUndefined();
  });
  it('fait dériver chaque nappe sur sa propre copie de texture et restaure au démontage', () => {
    const root = new THREE.Group(); const shared = new THREE.Texture();
    const fog = layer(root, 'fog', shared); const fog1 = layer(root, 'fog1', shared); const island = layer(root, 'island', shared);
    const effects = createV4Fog(root);
    expect(fog.material.map).not.toBe(shared); expect(island.material.map).toBe(shared);
    effects.update(2);
    expect(fog.material.map!.offset.x).toBeCloseTo(.1); expect(fog1.material.map!.offset.x).toBeCloseTo(-.04);
    effects.update(2, true); expect(fog.material.map!.offset.x).toBe(0);
    effects.dispose(); expect(fog.material.map).toBe(shared); expect(fog1.material.map).toBe(shared);
  });
});
