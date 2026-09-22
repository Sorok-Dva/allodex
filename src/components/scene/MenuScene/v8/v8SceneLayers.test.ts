import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { BORROWED_FIRE_SPEEDS, prepareV8Layers, scrollSpeedOf } from './v8SceneLayers';

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
    expect(beam.material.map!.offset.x).toBeCloseTo(-.4); // le contenu avance vers +u
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
    expect(first.material.map!.offset.x).toBeCloseTo(-.1);
    expect(second.material.map).toBe(first.material.map);
    expect(second.material).toBe(first.material);
    layers.dispose();
  });
  it('sépare un matériau partagé par des éléments de vitesses différentes (braises, cascade)', () => {
    // `Noise03White03` additif est un seul matériau glTF pour Statue_glow (0,1 ; 0,1),
    // Stone_hotspot (0,1 ; 0,1), fire_spots (0 ; 0,3) et group3_Fire1 (0,02 ; 0).
    const root = new THREE.Group();
    const original = new THREE.Texture();
    const glow = mesh(root, 'Statue_glow', 0, original, [.1, .1]);
    const shared = glow.material;
    const hotspot = mesh(root, 'Stone_hotspot', 1, original, [.1, .1]); hotspot.material = shared;
    const embers = mesh(root, 'fire_spots', 2, original, [0, .3]); embers.material = shared;
    const flame = mesh(root, 'group3_Fire1', 3, original, [.02, 0]); flame.material = shared;
    const layers = prepareV8Layers(root);
    expect(hotspot.material).toBe(shared);
    expect(embers.material).not.toBe(shared);
    expect(flame.material).not.toBe(shared);
    expect(embers.material).not.toBe(flame.material);
    expect(embers.material.blending).toBe(shared.blending);
    layers.update(1, false);
    // Texture non retournée (repeat 1 ; 1) : décalage = −vitesse × t sur les deux axes.
    expect(shared.map!.offset.toArray()).toEqual([expect.closeTo(-.1), expect.closeTo(-.1)]);
    expect(embers.material.map!.offset.toArray()).toEqual([0, expect.closeTo(-.3)]);
    expect(flame.material.map!.offset.toArray()).toEqual([expect.closeTo(-.02), 0]);
    // Les trois textures défilantes sont des clones indépendants de l'image d'origine.
    expect(new Set([shared.map, embers.material.map, flame.material.map]).size).toBe(3);
    expect(embers.material.map).not.toBe(original);
    const disposeClone = vi.spyOn(embers.material, 'dispose');
    layers.dispose();
    expect(shared.map).toBe(original);
    expect(embers.material).toBe(shared);
    expect(flame.material).toBe(shared);
    expect(disposeClone).toHaveBeenCalledOnce();
  });
  it('fait avancer le contenu dans le sens de la vitesse, sur u comme sur v', () => {
    // Un motif fixe de la texture, à la coordonnée c, s'affiche là où repeat × uv + offset = c.
    const root = new THREE.Group();
    const flipped = new THREE.Texture(); flipped.repeat.y = -1; flipped.offset.y = 1; // comme prepareTexture
    const water = mesh(root, 'waterfall_water', 0, flipped, [.5, 0]);
    const steam = mesh(root, 'watrefall_steam', 1, flipped, [0, .2]);
    const layers = prepareV8Layers(root);
    const shown = (map: THREE.Texture, c: number, axis: 'x' | 'y') => (c - map.offset[axis]) / map.repeat[axis];
    layers.update(0, false);
    const water0 = shown(water.material.map!, .5, 'x'), steam0 = shown(steam.material.map!, .5, 'y');
    layers.update(.5, false);
    // +u de la cascade pointe vers le bas : elle tombe ; +v de la vapeur pointe vers le haut : elle monte.
    expect(shown(water.material.map!, .5, 'x') - water0).toBeCloseTo(.25);
    expect(shown(steam.material.map!, .5, 'y') - steam0).toBeCloseTo(.1);
    layers.dispose();
  });
  it('emprunte un défilement aux grandes langues de feu, et à elles seules', () => {
    expect(BORROWED_FIRE_SPEEDS).toEqual({ group3_Fire2: [-.3, 0], group3_Fire3: [-.24, 0], group3_Fire4: [-.18, 0] });
    expect(scrollSpeedOf('group3_Fire2', [0, 0])).toEqual([-.3, 0]);
    expect(scrollSpeedOf('group3_Fire1', [.02, 0])).toEqual([.02, 0]); // vitesse native conservée
    expect(scrollSpeedOf('group3_FireGlow', [0, 0])).toEqual([0, 0]);
    expect(scrollSpeedOf('glow_add', [0, 0])).toEqual([0, 0]);

    // Dans le glb, Fire2 et Fire3 partagent `Lightning10_2White` additif, sans vitesse native.
    const root = new THREE.Group();
    const lightning = new THREE.Texture(); lightning.repeat.y = -1; lightning.offset.y = 1;
    const fire2 = mesh(root, 'group3_Fire2', 0, lightning, [0, 0]);
    const fire3 = mesh(root, 'group3_Fire3', 1, lightning, [0, 0]); fire3.material = fire2.material;
    const fire4 = mesh(root, 'group3_Fire4', 2, new THREE.Texture(), [0, 0]);
    const glowMap = new THREE.Texture();
    const glow = mesh(root, 'group3_FireGlow', 3, glowMap, [0, 0]);
    const halo = mesh(root, 'glow_add', 4, glowMap, [0, 0]);
    const layers = prepareV8Layers(root);
    expect(fire2.material).not.toBe(fire3.material); // deux vitesses : deux matériaux
    layers.update(1, false);
    // +u pointe vers le bas sur ces couches : un décalage u positif fait monter le feu.
    expect(fire2.material.map!.offset.toArray()).toEqual([expect.closeTo(.3), 1]);
    expect(fire3.material.map!.offset.toArray()).toEqual([expect.closeTo(.24), 1]);
    expect(fire4.material.map!.offset.toArray()).toEqual([expect.closeTo(.18), 0]);
    expect(glow.material.map).toBe(glowMap);
    expect(halo.material.map).toBe(glowMap);
    expect(glowMap.offset.toArray()).toEqual([0, 0]);
    layers.dispose();
    expect(fire2.material.map).toBe(lightning);
    expect(fire3.material).toBe(fire2.material);
  });
});
