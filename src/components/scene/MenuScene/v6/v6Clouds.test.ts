import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { BORROWED_SPEEDS, cloudSpeed, createV6Clouds } from './v6Clouds';
import { hooks } from './hooks';

/** Une nappe : le maillage porte le nom de l'élément du xdb, comme dans le `.glb` exporté. */
function layer(root: THREE.Object3D, element: string, material: THREE.MeshBasicMaterial) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), material);
  mesh.geometry.userData.element = element;
  root.add(mesh);
  return mesh;
}

/** Familles de matériaux du xdb : les éléments qui partagent un matériau dans l'export. */
const FAMILIES: Record<string, string[]> = {
  BackClouds_01: ['Clouds_Dark_02', 'Clouds_Dark_03', 'Clouds_Dark_05', 'Clouds_Front_Rays1',
    'Mountain_Clouds_01', 'Mountain_Clouds_02'],
  Ferris01_Clouds_Up: ['Clouds_Ring_05', 'Clouds_Dark_01', 'Clouds_Front_Rays', 'Clouds_Front_Rays2'],
  MidClouds_01: ['Clouds_Mid', 'Clouds_Mid1'],
  Noise01White_add: ['Sun_Rays_Add', 'Lab_Add'],
};

describe('nuages et brume 6.0', () => {
  it('emprunte à la 7.0 les vitesses des nappes, et rien pour le décor peint', () => {
    expect(cloudSpeed('Clouds_Ring_01')![0]).toBeCloseTo(0.01);   // Back_Cloud_01
    expect(cloudSpeed('Clouds_Ring_05')![0]).toBeCloseTo(0.02);   // Back_Cloud_06
    expect(cloudSpeed('Clouds_Mid')![0]).toBeCloseTo(-0.02);      // à contresens, ralentie sur demande
    // Les rayons Noise01White ont un u constant : c'est v qui porte les stries.
    expect(cloudSpeed('Sun_Rays_01')).toEqual([0, 0.04]);         // Ground_lights
    expect(cloudSpeed('Sun_Rays_Add')).toEqual([0, 0.04]);
    for (const element of ['Sky_Back', 'Lab', 'Railway', 'Train', 'Trees', 'Pillar_02', 'House_01',
      'Mountains_04', 'Front_Rocks', 'Flag1']) {
      expect(cloudSpeed(element)).toBeUndefined();
    }
  });

  it('donne la même vitesse aux éléments qui partagent un matériau dans l’export', () => {
    for (const elements of Object.values(FAMILIES)) {
      const speeds = elements.map(element => BORROWED_SPEEDS[element]);
      for (const speed of speeds) expect(speed).toBeDefined();
      for (const speed of speeds) expect(speed).toEqual(speeds[0]);
    }
  });

  it('fait dériver chaque nappe sur sa propre copie de texture et restaure au démontage', () => {
    const root = new THREE.Group();
    const shared = new THREE.Texture();
    const clouds = layer(root, 'Clouds_Ring_01', new THREE.MeshBasicMaterial({ map: shared }));
    const mist = layer(root, 'Clouds_Mid', new THREE.MeshBasicMaterial({ map: shared }));
    const rays = layer(root, 'Sun_Rays_01', new THREE.MeshBasicMaterial({ map: shared }));
    const rock = layer(root, 'Front_Rocks', new THREE.MeshBasicMaterial({ map: shared }));
    const effects = createV6Clouds(root);
    expect(clouds.material.map).not.toBe(shared);
    expect(rock.material.map).toBe(shared);
    effects.update(10);
    expect(clouds.material.map!.offset.x).toBeCloseTo(0.1);
    expect(mist.material.map!.offset.x).toBeCloseTo(-0.2);
    expect(rays.material.map!.offset.y).toBeCloseTo(-0.4);
    effects.update(10, true);   // mouvement réduit : image figée à t = 0
    expect(clouds.material.map!.offset.x).toBe(0);
    effects.dispose();
    expect(clouds.material.map).toBe(shared);
    expect(rays.material.map).toBe(shared);
  });

  it('défile dans le sens du client malgré le retournement des textures du crochet 6.0', () => {
    const root = new THREE.Group();
    const texture = new THREE.Texture();
    hooks.prepareTexture!(texture);                    // repeat.y = -1, offset.y = 1
    const rays = layer(root, 'Sun_Rays_01', new THREE.MeshBasicMaterial({ map: texture }));
    const effects = createV6Clouds(root);
    effects.update(5);
    // Échantillonné : v' = -v + offset.y = (1 - v) - t·vitesse, soit le (v + t·vitesse) du client.
    expect(rays.material.map!.repeat.y).toBe(-1);
    expect(rays.material.map!.offset.y).toBeCloseTo(1 - 5 * 0.04);
    effects.dispose();
  });
});
