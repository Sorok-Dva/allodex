import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { prepareV7Layers } from './v7SceneLayers';

function mesh(parent: THREE.Object3D, element: string, order: number, map = new THREE.Texture()) {
  const result = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map }));
  result.geometry.userData.element = element;
  result.renderOrder = order;
  parent.add(result);
  return result;
}
describe('V7 scene layers', () => {
  it('garde navires lointains et réacteurs lointains derrière toutes les coques proches', () => {
    const root = new THREE.Group();
    const front = new THREE.Group(); front.name = 'AMM_7_0_FrontShips'; root.add(front);
    const distant = new THREE.Group(); distant.name = 'AMM_7_0_Ships_Attack'; root.add(distant);
    const hull = mesh(front, 'Ship_L', -450);
    const engine = mesh(front, 'Engine_Glow01', -650);
    const rearGlow = mesh(front, 'Engine_Back01', -300);
    const small = mesh(distant, 'Ship_R', -100);
    const smallEngine = mesh(distant, 'Engine_Glow01', -800);
    const layers = prepareV7Layers(root);
    expect(small.renderOrder).toBeLessThan(smallEngine.renderOrder);
    expect(smallEngine.renderOrder).toBeLessThan(hull.renderOrder);
    expect(hull.renderOrder).toBeLessThan(engine.renderOrder);
    expect(rearGlow.renderOrder).toBeLessThan(hull.renderOrder);
    expect(distant.scale.toArray()).toEqual([.82, .82, .82]);
    expect(front.scale.toArray()).toEqual([1, 1, 1]);
    layers.dispose();
  });
  it('anime les UV natives indépendamment sans déplacer les textures partagées du paysage', () => {
    const root = new THREE.Group();
    const original = new THREE.Texture(); original.offset.set(0, 1); original.repeat.y = -1;
    const ground = mesh(root, 'Ground', -500, original);
    const mist = mesh(root, 'Back_Myst', -700, original);
    mist.geometry.userData.uvScroll = [-.05, .02];
    const clouds = mesh(root, 'Back_Cloud_03', -600, original);
    clouds.geometry.userData.uvScroll = [.02, 0];
    const layers = prepareV7Layers(root);
    const moving = mist.material.map!;
    expect(moving).not.toBe(original);
    expect(moving.wrapS).toBe(THREE.RepeatWrapping);
    layers.update(4, false);
    expect(moving.offset.x).toBeCloseTo(-.2); expect(moving.offset.y).toBeCloseTo(.92);
    expect(clouds.material.map!.offset.x).toBeCloseTo(.08);
    expect(ground.material.map!.offset.toArray()).toEqual([0, 1]);
    layers.update(4, false); expect(moving.offset.x).toBeCloseTo(-.2); // pas de dérive cumulative
    layers.update(4, true); expect(moving.offset.toArray()).toEqual([0, 1]);
    const dispose = vi.spyOn(moving, 'dispose');
    layers.dispose(); expect(dispose).toHaveBeenCalledOnce(); expect(mist.material.map).toBe(original);
  });
});
