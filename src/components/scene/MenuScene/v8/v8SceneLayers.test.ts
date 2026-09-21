import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { prepareV8Layers } from './v8SceneLayers';

function mesh(parent: THREE.Object3D, element: string, order: number, map = new THREE.Texture(), uvScroll?: number[]) {
  const result = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map }));
  result.geometry.userData.element = element;
  if (uvScroll) result.geometry.userData.uvScroll = uvScroll;
  result.renderOrder = order;
  parent.add(result);
  return result;
}

describe('V8 scene layers', () => {
  it('peint les éléments dans l\'ordre du xdb (sortMode OFFSETS), pas par profondeur moyenne', () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); group.name = 'AMM_8_0_mesh'; root.add(group);
    // Le tri générique avait mis les nuages de fond (arc proche) devant la statue.
    const sky = mesh(group, 'Back_Color2', -269);
    const clouds = mesh(group, 'Back_Cloud_06', -241);
    const statue = mesh(group, 'Statue', -253);
    const frontClouds = mesh(group, 'front_clouds', -216);
    const fire = mesh(group, 'group3_Fire1', -267);
    const layers = prepareV8Layers(root);
    expect(layers.count).toBe(5);
    expect(sky.renderOrder).toBeLessThan(clouds.renderOrder);
    expect(clouds.renderOrder).toBeLessThan(statue.renderOrder);
    expect(statue.renderOrder).toBeLessThan(frontClouds.renderOrder);
    expect(frontClouds.renderOrder).toBeLessThan(fire.renderOrder);
    layers.dispose();
  });
  it('ignore les maillages sans élément natif', () => {
    const root = new THREE.Group();
    const plain = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    plain.renderOrder = 42; root.add(plain);
    const layers = prepareV8Layers(root);
    expect(layers.count).toBe(0);
    expect(plain.renderOrder).toBe(42);
  });
  it('fait défiler les UV natives dans le sens du client, sur une texture indépendante', () => {
    const root = new THREE.Group();
    const original = new THREE.Texture(); original.repeat.y = -1; original.offset.y = 1; // retournée par prepareTexture
    const landmark = mesh(root, 'back_landmark', 0, original);
    const steam = mesh(root, 'watrefall_steam', 1, original, [0, .2]);
    const beam = mesh(root, 'In_Big_Add', 2, original, [.2, 0]);
    const still = mesh(root, 'Statue', 3, original, [0, 0]);
    const layers = prepareV8Layers(root);
    const moving = steam.material.map!;
    expect(moving).not.toBe(original);
    expect(moving.wrapS).toBe(THREE.RepeatWrapping);
    expect(moving.wrapT).toBe(THREE.RepeatWrapping);
    layers.update(2, false);
    expect(moving.offset.toArray()).toEqual([0, expect.closeTo(1.4)]); // texture retournée : la vapeur monte
    expect(beam.material.map!.offset.x).toBeCloseTo(.4);
    expect(landmark.material.map!.offset.toArray()).toEqual([0, 1]);
    expect(still.material.map).toBe(original);
    layers.update(2, false); expect(moving.offset.y).toBeCloseTo(1.4); // pas de dérive cumulative
    layers.update(7, false); expect(moving.offset.y).toBeCloseTo(1.4); // modulo 1 : 1,4 → 0,4
    layers.update(2, true); expect(moving.offset.toArray()).toEqual([0, 1]); // mouvements réduits
    const dispose = vi.spyOn(moving, 'dispose');
    layers.dispose();
    expect(dispose).toHaveBeenCalledOnce();
    expect(steam.material.map).toBe(original);
  });
  it('ne fait défiler qu\'une fois un matériau partagé par plusieurs éléments', () => {
    const root = new THREE.Group();
    const first = mesh(root, 'Back_Cloud_06', 0, new THREE.Texture(), [.01, 0]);
    const second = mesh(root, 'Back_Cloud_06', 1, first.material.map!, [.01, 0]);
    second.material = first.material;
    const layers = prepareV8Layers(root);
    layers.update(10, false);
    expect(first.material.map!.offset.x).toBeCloseTo(.1);
    expect(second.material.map).toBe(first.material.map);
    layers.dispose();
  });
});
